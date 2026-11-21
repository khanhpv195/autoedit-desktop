import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from autoedit.project import DEFAULT_CTA
from autoedit.render.compose import HOOK_SECONDS
from autoedit.transcript import Word, resolve_edits, speech_duration

PAD_BEFORE = 0.05
PAD_AFTER = 0.08
MIN_SEGMENT = 0.4
TOUCH = 0.05        # ranges whose edges are this close count as touching
MIN_KEEP_RATIO = 0.30
HOOK_MAX_WORDS = 5
BROLL_MIN, BROLL_MAX = 1.5, 4.0
BROLL_PER_SECONDS = 3.0     # soft rule: at most one b-roll per 3 s of output


class EdlError(ValueError):
    pass


@dataclass
class Range:
    start: float
    end: float
    reason: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Hook:
    start: float | None     # None: hook text only, laid over whatever plays first (nothing moved)
    end: float | None
    text: str

    @property
    def moved(self) -> bool:
        return self.start is not None and self.end is not None


@dataclass
class CaptionFix:
    at: float
    wrong: str
    right: str


@dataclass
class Emphasis:
    at: float
    word: str


@dataclass
class Broll:
    image: str      # file name from the project's images
    at: float       # timeline seconds, inside a kept range
    dur: float


@dataclass
class VoiceCue:
    at: float       # timeline seconds, inside a kept range (same convention as b-roll)
    text: str


@dataclass
class VoiceLine:
    """A voiceover line synthesized in this session (the `voiceover` tool)."""
    at: float
    text: str
    path: Path | None
    duration: float
    words: list = field(default_factory=list)     # [(text, start, end)] relative to the line start


def voice_key(at: float, text: str) -> tuple[float, str]:
    return round(float(at), 3), str(text).strip()


@dataclass
class Edl:
    keep: list[Range]
    hook: Hook | None = None
    caption_fixes: list[CaptionFix] = field(default_factory=list)
    emphasis: list[Emphasis] = field(default_factory=list)
    broll: list[Broll] = field(default_factory=list)
    cta_text: str = DEFAULT_CTA
    music_use: bool = True
    music_duck_db: float = -14.0
    voiceover: list[VoiceCue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "keep": [asdict(r) for r in self.keep],
            "hook": self._hook_dict(),
            "caption_fixes": [asdict(c) for c in self.caption_fixes],
            "emphasis": [asdict(e) for e in self.emphasis],
            "broll": [asdict(b) for b in self.broll],
            "cta_text": self.cta_text,
            "music": {"use": self.music_use, "duck_db": self.music_duck_db},
            "voiceover": [asdict(c) for c in self.voiceover],
        }

    def _hook_dict(self) -> dict | None:
        if not self.hook:
            return None
        if not self.hook.moved:
            return {"text": self.hook.text}
        return {"move_to_front": [self.hook.start, self.hook.end], "text": self.hook.text}

    def ordered(self) -> list[Range]:
        """Play order: the keep list as given (free shot order), with a moved hook range first."""
        if not self.hook or not self.hook.moved:
            return list(self.keep)
        h = Range(self.hook.start, self.hook.end, "hook")
        rest: list[Range] = []
        for r in self.keep:
            if r.end <= h.start or r.start >= h.end:
                rest.append(r)
                continue
            for a, b in ((r.start, h.start), (h.end, r.end)):
                if b - a >= MIN_SEGMENT:
                    rest.append(Range(a, b, r.reason))
        return [h] + rest

    def output_span(self, at: float, dur: float) -> tuple[float, float] | None:
        """Map a timeline moment to output time through the ordered ranges. Returns (start, end) in output seconds,
        or None if `at` is in no kept range. The window is cut at the end of the range it starts in."""
        offset = 0.0
        for r in self.ordered():
            if r.start - 1e-9 <= at < r.end - 1e-9:
                start = offset + (at - r.start)
                return start, min(start + dur, offset + r.duration)
            offset += r.duration
        return None

    def output_time(self, t: float) -> float | None:
        span = self.output_span(t, 0.0)
        return span[0] if span else None

    def output_duration(self) -> float:
        return sum(r.duration for r in self.ordered())


FPS = 30


def _grid(t: float, lo: float, hi: float, dur: float) -> float:
    """Nearest 1/30 s frame boundary inside [lo, hi] (never into a neighbouring word); t itself if none fits."""
    hi = min(hi, dur)
    lo = max(lo, 0.0)
    g = round(t * FPS) / FPS
    if lo - 1e-9 <= g <= hi + 1e-9:
        return min(max(g, lo), hi)
    for cand in (math.floor(t * FPS) / FPS, math.ceil(t * FPS) / FPS):
        if lo - 1e-9 <= cand <= hi + 1e-9:
            return cand
    return t


def _free_gap(t: float, words: list[Word]) -> tuple[float, float]:
    lo = max((w.end for w in words if w.end <= t + 1e-9), default=0.0)
    hi = min((w.start for w in words if w.start >= t - 1e-9), default=float("inf"))
    return lo, max(lo, hi)


def _snap_start(a: float, words: list[Word], dur: float) -> float:
    """An edge inside (or within the pad of) a word moves to that word's start, padded but clamped to the
    midpoint of the gap before it. An edge in silence stays where the agent put it (frame-aligned)."""
    for i, w in enumerate(words):
        if w.start - PAD_BEFORE <= a < w.end:
            lo = 0.0 if i == 0 else min(w.start, (words[i - 1].end + w.start) / 2)
            lo = max(lo, 0.0)
            return _grid(max(w.start - PAD_BEFORE, lo), lo, w.start, dur)
    lo, hi = _free_gap(a, words)
    return _grid(a, lo, hi, dur)


def _snap_end(b: float, words: list[Word], dur: float) -> float:
    for i in range(len(words) - 1, -1, -1):
        w = words[i]
        if w.start < b <= w.end + PAD_AFTER:
            hi = dur if i + 1 == len(words) else max(w.end, (w.end + words[i + 1].start) / 2)
            hi = min(hi, dur)
            return _grid(min(w.end + PAD_AFTER, hi), w.end, hi, dur)
    lo, hi = _free_gap(b, words)
    return _grid(b, lo, hi, dur)


def _snap_pad(a: float, b: float, words: list[Word], dur: float) -> tuple[float, float]:
    ws = sorted(words, key=lambda w: w.start)
    return _snap_start(a, ws, dur), _snap_end(b, ws, dur)


def _speech_in(ranges: list[Range], words: list[Word]) -> float:
    total = 0.0
    for w in words:
        for r in ranges:
            total += max(0.0, min(w.end, r.end) - max(w.start, r.start))
    return total


def _validate_broll(raw: list, kept: list[Range], hook: Hook | None, image_names: list[str],
                    notes: list[str]) -> list[Broll]:
    """Image must be a project image (error: the agent can fix it). Everything else is corrected or dropped with a
    note: dur clamped to 1.5-4 s, `at` must be inside a kept range, never over the hook's first seconds, no two
    overlapping, at most one per 3 s of output."""
    if not raw:
        return []
    probe_edl = Edl(keep=kept, hook=hook)
    total = probe_edl.output_duration()
    out: list[Broll] = []
    windows: list[tuple[float, float]] = []
    for b in sorted((x for x in raw), key=lambda x: float(x["at"])):
        image, at = str(b["image"]).strip(), float(b["at"])
        if image not in image_names:
            names = ", ".join(image_names) or "(no images in this project)"
            raise EdlError(f"broll image {image!r} is not one of the project images: {names}")
        raw_dur = b.get("dur")
        dur = min(BROLL_MAX, max(BROLL_MIN, 2.5 if raw_dur is None else float(raw_dur)))
        span = probe_edl.output_span(at, dur)
        if span is None:
            notes.append(f"dropped broll {image} at {at:.2f}: not inside a kept range")
            continue
        o_start, o_end = span
        if o_start < HOOK_SECONDS:
            # push the start to HOOK_SECONDS in OUTPUT time, then map back to a timeline `at` in the same kept range
            shift = HOOK_SECONDS - o_start
            new_at = at + shift
            r = next((r for r in probe_edl.ordered() if r.start - 1e-9 <= at < r.end - 1e-9), None)
            if r is None or new_at >= r.end - 1e-9:
                notes.append(f"dropped broll {image}: it would cover the hook's first {HOOK_SECONDS}s")
                continue
            at = new_at
            span = probe_edl.output_span(at, dur)
            if span is None or span[0] < HOOK_SECONDS - 1e-6:
                notes.append(f"dropped broll {image}: it would cover the hook's first {HOOK_SECONDS}s")
                continue
            o_start, o_end = span
        if o_end - o_start < BROLL_MIN - 1e-6:
            notes.append(f"dropped broll {image} at {at:.2f}: less than {BROLL_MIN}s fits before the next cut")
            continue
        if any(o_start < e and o_end > s for s, e in windows):
            notes.append(f"dropped broll {image} at {at:.2f}: overlaps another broll")
            continue
        if len(out) >= max(1, int(total / BROLL_PER_SECONDS)):
            notes.append(f"dropped broll {image} at {at:.2f}: more than 1 per {BROLL_PER_SECONDS:.0f}s of output")
            continue
        out.append(Broll(image, round(at, 3), round(o_end - o_start, 3)))
        windows.append((o_start, o_end))
    return out


def _merge_and_check(ranges: list[Range], keep_raw: list) -> list[tuple[int, Range]]:
    """Free shot order: the list order is the play order. Works on the agent's RAW numbers (before snap/pad) so a
    take split mid-word is not mistaken for an overlap. A list neighbour that starts inside (or within TOUCH of the
    end of) the previous range continues it and merges; any other overlap beyond TOUCH means the same footage
    would play twice: reject it, quoting the agent's own numbers."""
    merged: list[tuple[int, Range]] = []
    for i, r in enumerate(ranges):
        prev = merged[-1][1] if merged else None
        if prev is not None and prev.start - 1e-9 <= r.start <= prev.end + TOUCH:
            prev.end = max(prev.end, r.end)
        else:
            merged.append((i, Range(r.start, r.end, r.reason)))

    def raw(i: int) -> str:
        return f"{float(keep_raw[i]['start']):g}–{float(keep_raw[i]['end']):g}"

    for x, (i, a) in enumerate(merged):
        for j, b in merged[:x]:
            if min(a.end, b.end) - max(a.start, b.start) > TOUCH:
                raise EdlError(f"keep[{i}] ({raw(i)}) chồng lên keep[{j}] ({raw(j)}); mỗi đoạn chỉ dùng một lần")
    return merged


def _clamp_padding_overlaps(ranges: list[Range]) -> None:
    """After snap/pad, two ranges that did not overlap as given may touch into each other's padding: the one
    later in the source starts where the earlier one ends (no footage plays twice, no error)."""
    for x, a in enumerate(ranges):
        for b in ranges[:x]:
            early, late = (a, b) if a.start <= b.start else (b, a)
            if late.start < early.end:
                late.start = early.end


def validate_edl(raw: dict, words: list[Word], clip_duration: float,
                 image_names: tuple[str, ...] | list[str] = (), *,
                 default_cta: str = DEFAULT_CTA, voiceover_on: bool = False,
                 voice_lines: dict | None = None) -> tuple[Edl, list[str]]:
    notes: list[str] = []
    keep_raw = raw.get("keep") or []
    if not keep_raw:
        raise EdlError("keep must contain at least one range")
    ranges: list[Range] = []
    for k in keep_raw:
        a, b = float(k["start"]), float(k["end"])
        if not (0 <= a < b <= clip_duration + 0.01):
            raise EdlError(f"range {a}-{b} is outside 0-{clip_duration:.2f} or inverted")
        ranges.append(Range(a, min(b, clip_duration), str(k.get("reason", ""))))
    merged = _merge_and_check(ranges, keep_raw)
    for _, r in merged:
        r.start, r.end = _snap_pad(r.start, r.end, words, clip_duration)
    _clamp_padding_overlaps([r for _, r in merged])
    kept = []
    for _, r in merged:
        if r.duration < MIN_SEGMENT:
            notes.append(f"dropped {r.start:.2f}-{r.end:.2f}: shorter than {MIN_SEGMENT}s")
        else:
            kept.append(r)
    if not kept:
        raise EdlError("every range is shorter than 0.4s")

    total_speech = speech_duration(words)
    if total_speech > 0 and not voiceover_on:      # with voiceover the original audio is muted
        ratio = _speech_in(kept, words) / total_speech
        if ratio < MIN_KEEP_RATIO:
            raise EdlError(f"keeps only {ratio:.0%} of the speech; keep at least 30%")

    hook = None
    if raw.get("hook"):
        h = raw["hook"]
        text = str(h.get("text", "")).strip()
        if not text:
            raise EdlError("hook text must not be empty (use hook: null for no hook)")
        if len(text.split()) > HOOK_MAX_WORDS:
            raise EdlError(f"hook text must be at most {HOOK_MAX_WORDS} words")
        if h.get("move_to_front"):
            a, b = (float(x) for x in h["move_to_front"])
            if not (0 <= a < b <= clip_duration + 0.01):
                raise EdlError("hook range is outside the clip or inverted")
            a, b = _snap_pad(a, min(b, clip_duration), words, clip_duration)
            hook = Hook(a, b, text)
        else:
            hook = Hook(None, None, text)       # text over the first 2.5 s of whatever plays first

    fixes = [CaptionFix(float(c["at"]), str(c["wrong"]).strip(), str(c["right"]).strip())
             for c in raw.get("caption_fixes") or []]
    emph = [Emphasis(float(e["at"]), str(e["word"]).strip()) for e in raw.get("emphasis") or []]
    if any(not f.wrong or not f.right for f in fixes):
        raise EdlError("caption_fixes need non-empty wrong and right text")
    if any(not e.word for e in emph):
        raise EdlError("emphasis needs a non-empty word")

    if not voiceover_on:    # with voiceover, fixes/emphasis apply to the voiceover words (matched at render)
        notes += resolve_edits(words, fixes, emph)[2]

    broll = _validate_broll(raw.get("broll") or [], kept, hook, list(image_names), notes)

    music = raw.get("music") or {}
    duck = float(music.get("duck_db", -14.0))
    edl = Edl(
        keep=kept,
        hook=hook,
        caption_fixes=fixes,
        emphasis=emph,
        broll=broll,
        cta_text=str(raw.get("cta_text") or "").strip() or default_cta,
        music_use=bool(music.get("use", True)),
        music_duck_db=min(-6.0, max(-24.0, duck)),
    )
    edl.voiceover = _validate_voiceover(raw.get("voiceover") or [], edl, voice_lines or {})
    return edl, notes


def _validate_voiceover(raw: list, edl: Edl, voice_lines: dict) -> list[VoiceCue]:
    """Every cue must be a line made by the `voiceover` tool in this session; lines must sit inside kept footage,
    not overlap each other and end before the video ends. Returned in output-time order."""
    if not raw:
        return []
    total = edl.output_duration()
    placed: list[tuple[float, float, VoiceCue]] = []
    for c in raw:
        key = voice_key(c["at"], c["text"])
        line = voice_lines.get(key)
        if line is None:
            raise EdlError(f"voiceover line {key[1]!r} at {key[0]} was not generated: call the voiceover tool with "
                           "exactly this at/text first")
        start = edl.output_time(key[0])
        if start is None:
            raise EdlError(f"voiceover line {key[1]!r}: at {key[0]} is not inside a kept range")
        if start + line.duration > total + 0.05:
            raise EdlError(f"voiceover line {key[1]!r} runs past the end of the video ({start:.2f}+"
                           f"{line.duration:.2f}s > {total:.2f}s); move it earlier or shorten it")
        placed.append((start, start + line.duration, VoiceCue(key[0], key[1])))
    placed.sort(key=lambda x: x[0])
    for (a0, a1, a), (b0, _, b) in zip(placed, placed[1:]):
        if b0 < a1 - 0.01:
            raise EdlError(f"voiceover lines overlap: {a.text!r} plays {a0:.2f}-{a1:.2f}s and {b.text!r} starts "
                           f"at {b0:.2f}s; leave 0.3 s between lines")
    return [c for _, _, c in placed]
