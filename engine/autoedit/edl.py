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
    position: str = "middle"    # where the card sits: top / middle / lower (keep it off the face)

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
    image: str      # file name from the project's images ("" for a video cutaway)
    at: float       # timeline seconds, inside a kept range
    dur: float
    shot: float | None = None   # video cutaway: timeline second where the shot starts (picture only, speech goes on)

    def to_dict(self) -> dict:
        if self.shot is None:
            return {"image": self.image, "at": self.at, "dur": self.dur}
        return {"shot": self.shot, "at": self.at, "dur": self.dur}


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
            "broll": [b.to_dict() for b in self.broll],
            "cta_text": self.cta_text,
            "music": {"use": self.music_use, "duck_db": self.music_duck_db},
            "voiceover": [asdict(c) for c in self.voiceover],
        }

    def _hook_dict(self) -> dict | None:
        if not self.hook:
            return None
        d = {"text": self.hook.text, "position": self.hook.position}
        if self.hook.moved:
            d["move_to_front"] = [self.hook.start, self.hook.end]
        return d

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
    midpoint of the gap before it. An edge that is both inside a word and inside a neighbour's pad goes to the
    neighbour ("stop after 'hình'" given 30 ms into the next word). An edge in silence stays where the agent put it (frame-aligned)."""
    for i, w in enumerate(words):
        if i + 1 < len(words) and w.start < a and words[i + 1].start - PAD_BEFORE <= a:
            continue          # also inside the next word's pad: the agent meant the next word, not this tail
        if w.start - PAD_BEFORE <= a < w.end:
            lo = 0.0 if i == 0 else min(w.start, (words[i - 1].end + w.start) / 2)
            lo = max(lo, 0.0)
            return _grid(max(w.start - PAD_BEFORE, lo), lo, w.start, dur)
    lo, hi = _free_gap(a, words)
    return _grid(a, lo, hi, dur)


def _snap_end(b: float, words: list[Word], dur: float) -> float:
    for i in range(len(words) - 1, -1, -1):
        w = words[i]
        if i > 0 and b < w.end and b <= words[i - 1].end + PAD_AFTER:
            continue          # also inside the previous word's pad: the agent meant to stop after that word
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


CONNECTIVES = {"và", "mà", "thì", "là", "với", "hoặc", "nhưng", "còn", "kèm", "cho", "của"}
SENTENCE_GAP = 0.12     # a pause shorter than this between two words means the sentence goes on


def _starts_sentence(w: Word) -> bool:
    return w.text[:1].isupper()


def sentence_edge_notes(kept: list[Range], words: list[Word]) -> list[str]:
    """Whisper capitalises sentence starts. A range that opens on a lowercase word or number glued to the word before
    it starts mid-sentence (a stray "2027" or "size" in the captions); a video whose last range stops right before a
    lowercase word ends mid-sentence. Both are notes only: the agent decides."""
    if not words or not any(_starts_sentence(w) for w in words):
        return []
    notes = []
    last = kept[-1] if kept else None      # play order: only the video's last range is checked for a cut-off end
    for r in kept:
        idx = [i for i, w in enumerate(words) if r.start <= (w.start + w.end) / 2 < r.end]
        if not idx:
            continue
        i, j = idx[0], idx[-1]
        if i > 0 and not _starts_sentence(words[i]) and words[i].start - words[i - 1].end < SENTENCE_GAP:
            k = i - 1           # walk back over glued words to where this sentence starts
            while k > 0 and not _starts_sentence(words[k]) and words[k].start - words[k - 1].end < SENTENCE_GAP:
                k -= 1
            hint = f"; this sentence starts at {words[k].start:.2f} ({words[k].text!r}): start there"
            nxt = next((w for w in words[i + 1:] if _starts_sentence(w) and w.start < r.end), None)
            if nxt:
                hint += f", or skip to the next sentence at {nxt.start:.2f} ({nxt.text!r})"
            notes.append(f"range {r.start:.2f}-{r.end:.2f} starts mid-sentence on {words[i].text!r} "
                         f"(after {words[i - 1].text!r}){hint}")
        if r is last and j + 1 < len(words) and not _starts_sentence(words[j + 1]) and words[j + 1].start - words[j].end < SENTENCE_GAP:
            k = next((k for k in range(j + 1, len(words)) if k + 1 == len(words) or _starts_sentence(words[k + 1])
                      or words[k + 1].start - words[k].end >= 0.3), len(words) - 1)
            rest = " ".join(w.text for w in words[j + 1:k + 1][:6])
            m = j               # trailing connectives ("... màn hình và") leave the video hanging
            while m > idx[0] and words[m].text.lower().strip(",.") in CONNECTIVES:
                m -= 1
            trim = f", or end at {words[m].end:.2f} after {words[m].text!r}" if m < j else ""
            notes.append(f"the video's last range {r.start:.2f}-{r.end:.2f} ends mid-sentence before {rest!r}; "
                         f"the sentence ends at {words[k].end:.2f}{trim}")
    return notes


def trim_dangling_end(kept: list[Range], words: list[Word], dur: float) -> tuple[list[Range], list[str]]:
    """The video must not end on a connective glued to the next word ("... màn hình và"): cut the last range (play
    order) back to the word before the trailing connectives. Agents put such an end a few ms into the connective."""
    if not kept or not words or not any(_starts_sentence(w) for w in words):
        return kept, []
    r = kept[-1]
    idx = [i for i, w in enumerate(words) if r.start <= (w.start + w.end) / 2 < r.end]
    if not idx:
        return kept, []
    j = idx[-1]
    glued = j + 1 < len(words) and not _starts_sentence(words[j + 1]) and words[j + 1].start - words[j].end < SENTENCE_GAP
    m = j
    while m > idx[0] and words[m].text.lower().strip(",.") in CONNECTIVES:
        m -= 1
    if not glued or m == j:
        return kept, []
    end = _snap_end(words[m].end, words, dur)
    if end - r.start < MIN_SEGMENT:
        return kept, []
    cut = " ".join(w.text for w in words[m + 1:j + 1])
    return kept[:-1] + [Range(r.start, end, r.reason)], [
        f"the last range now ends at {end:.2f} after {words[m].text!r}: a video must not end on {cut!r}"]


TAIL_MAX = 0.35         # a sentence tail this short ("... em vừa ra | thôi") is kept rather than cut off


def keep_short_tails(kept: list[Range], words: list[Word], dur: float) -> tuple[list[Range], list[str]]:
    """A range that stops one short word before its sentence ends (the word glued on, e.g. "thôi", "ạ") cuts the
    voice mid-flow and pops: extend it to the sentence end when that is <= TAIL_MAX away and overlaps nothing."""
    if not words or not any(_starts_sentence(w) for w in words):
        return kept, []
    out, notes = list(kept), []
    for n, r in enumerate(kept):
        idx = [i for i, w in enumerate(words) if r.start <= (w.start + w.end) / 2 < r.end]
        if not idx:
            continue
        j = idx[-1]
        if (j > idx[0] and _starts_sentence(words[j]) and j + 1 < len(words)
                and words[j + 1].start - words[j].end < SENTENCE_GAP and not _starts_sentence(words[j + 1])):
            end = _snap_end(words[j - 1].end, words, dur)       # "... hot luôn | Anh" : a stray next-sentence word
            out[n] = Range(r.start, end, r.reason)
            notes.append(f"range {r.start:.2f}-{r.end:.2f} now ends at {end:.2f}: it ended on {words[j].text!r}, "
                         "the first word of the next sentence")
            continue
        k = j
        while (k + 1 < len(words) and not _starts_sentence(words[k + 1])
               and words[k + 1].start - words[k].end < SENTENCE_GAP and words[k + 1].end - words[j].end <= TAIL_MAX):
            k += 1
        if k == j or not (k + 1 == len(words) or _starts_sentence(words[k + 1])
                          or words[k + 1].start - words[k].end >= SENTENCE_GAP):
            continue        # nothing glued on, or the sentence runs on longer than a short tail
        end = _snap_end(words[k].end, words, dur)
        if any(o is not r and o.start < end and r.end <= o.start for o in kept):
            continue        # would run into another kept range
        out[n] = Range(r.start, end, r.reason)
        tail = " ".join(w.text for w in words[j + 1:k + 1])
        notes.append(f"range {r.start:.2f}-{r.end:.2f} now ends at {end:.2f} to finish the sentence with {tail!r}")
    return out, notes


def keep_short_heads(kept: list[Range], words: list[Word], dur: float) -> tuple[list[Range], list[str]]:
    """Mirror of keep_short_tails: a range that starts one short word after its sentence starts ("Chân | gọi là
    vòng kiềng") opens on a fragment; pull its start back to the sentence start when that is <= TAIL_MAX away."""
    if not words or not any(_starts_sentence(w) for w in words):
        return kept, []
    out, notes = list(kept), []
    for n, r in enumerate(kept):
        idx = [i for i, w in enumerate(words) if r.start <= (w.start + w.end) / 2 < r.end]
        if not idx:
            continue
        i = k = idx[0]
        while (k > 0 and not _starts_sentence(words[k]) and words[k].start - words[k - 1].end < SENTENCE_GAP
               and words[i].start - words[k - 1].start <= TAIL_MAX):
            k -= 1
        if k == i or not _starts_sentence(words[k]):
            continue        # already on a sentence start, or the sentence began too long ago
        start = _snap_start(words[k].start, words, dur)
        if any(o is not r and o.end > start and o.end <= r.start for o in kept):
            continue        # would run into another kept range
        out[n] = Range(start, r.end, r.reason)
        head = " ".join(w.text for w in words[k:i])
        notes.append(f"range {r.start:.2f}-{r.end:.2f} now starts at {start:.2f} to open the sentence with {head!r}")
    return out, notes


HOOK_POSITIONS = ("top", "middle", "lower")


STATIC_MAX = 7.0        # seconds of one framing before a note asks for a cutaway


def static_notes(edl: "Edl") -> list[str]:
    """Stretches of kept footage longer than STATIC_MAX with no cut and no b-roll over them (timeline seconds)."""
    notes = []
    for r in edl.ordered():
        covered = sorted((b.at, b.at + b.dur) for b in edl.broll if r.start - 1e-9 <= b.at < r.end)
        t = r.start
        for a, e in covered + [(r.end, r.end)]:
            if a - t > STATIC_MAX:
                notes.append(f"timeline {t:.2f}-{a:.2f} shows one framing for {a - t:.1f}s: lay a cutaway over it "
                             "(`broll` with `shot` from another clip, or an image) every 3-6 s")
            t = max(t, e)
    return notes


def _shot_start(shot: float, dur: float, spans: list[tuple[str, float, float]], clip_duration: float) -> float:
    """A cutaway shot must play from one clip only: pull its start back so [shot, shot+dur] ends inside the clip
    it starts in (never past the source end, which would freeze the last frame)."""
    if not (0 <= shot < clip_duration):
        raise EdlError(f"broll shot {shot} is outside the timeline 0-{clip_duration:.2f}")
    a, b = next(((a, b) for _, a, b in spans if a - 1e-9 <= shot < b - 1e-9), (0.0, clip_duration))
    return round(max(a, min(shot, b - dur - 0.05)), 3)


def _validate_broll(raw: list, kept: list[Range], hook: Hook | None, image_names: list[str],
                    notes: list[str], spans: list | None = None, clip_duration: float = 0.0) -> list[Broll]:
    """Image must be a project image (error: the agent can fix it). Everything else is corrected or dropped with a
    note: dur clamped to 1.5-4 s, `at` must be inside a kept range, never over the hook's first seconds, no two
    overlapping, at most one per 3 s of output."""
    if not raw:
        return []
    probe_edl = Edl(keep=kept, hook=hook)
    total = probe_edl.output_duration()
    out: list[Broll] = []
    windows: list[tuple[float, float]] = []
    used = [(r.start, r.end) for r in probe_edl.ordered()]     # footage already on screen
    for b in sorted((x for x in raw), key=lambda x: float(x["at"])):
        image, at = str(b.get("image") or "").strip(), float(b["at"])
        shot = b.get("shot")
        if shot is None and not image:
            raise EdlError("each broll needs `image` (a project image) or `shot` (timeline second of a video shot)")
        if shot is not None:
            image = ""
            if not (0 <= float(shot) < clip_duration):
                raise EdlError(f"broll shot {shot} is outside the timeline 0-{clip_duration:.2f}")
        elif image not in image_names:
            names = ", ".join(image_names) or "(no images in this project)"
            raise EdlError(f"broll image {image!r} is not one of the project images: {names}")
        label = image or f"shot {float(shot):.2f}"
        raw_dur = b.get("dur")
        dur = min(BROLL_MAX, max(BROLL_MIN, 2.5 if raw_dur is None else float(raw_dur)))
        span = probe_edl.output_span(at, dur)
        if span is None:
            ranges = ", ".join(f"{r.start:.2f}-{r.end:.2f}" for r in probe_edl.ordered())
            notes.append(f"dropped broll {label} at {at:.2f}: not inside a kept range. `at` is a TIMELINE second "
                         f"(the source time of the speech it covers), not an output second; kept: {ranges}")
            continue
        o_start, o_end = span
        if o_end - o_start < BROLL_MIN - 1e-6:
            # too close to the end of its range: slide it back so it ends at the range end (same speech moment)
            r = next(r for r in probe_edl.ordered() if r.start - 1e-9 <= at < r.end - 1e-9)
            if r.duration >= BROLL_MIN:
                at = max(r.start, r.end - dur)
                o_start, o_end = probe_edl.output_span(at, dur)
        if o_start < HOOK_SECONDS:
            # push the start to HOOK_SECONDS in OUTPUT time, then map back to a timeline `at` in the same kept range
            shift = HOOK_SECONDS - o_start
            new_at = at + shift
            r = next((r for r in probe_edl.ordered() if r.start - 1e-9 <= at < r.end - 1e-9), None)
            if r is None or new_at >= r.end - 1e-9:
                notes.append(f"dropped broll {label}: it would cover the hook's first {HOOK_SECONDS}s")
                continue
            at = new_at
            span = probe_edl.output_span(at, dur)
            if span is None or span[0] < HOOK_SECONDS - 1e-6:
                notes.append(f"dropped broll {label}: it would cover the hook's first {HOOK_SECONDS}s")
                continue
            o_start, o_end = span
        if o_end - o_start < BROLL_MIN - 1e-6:
            notes.append(f"dropped broll {label} at {at:.2f}: less than {BROLL_MIN}s fits before the next cut")
            continue
        if any(o_start < e and o_end > s for s, e in windows):
            notes.append(f"dropped broll {label} at {at:.2f}: overlaps another broll")
            continue
        if len(out) >= max(1, int(total / BROLL_PER_SECONDS)):
            notes.append(f"dropped broll {label} at {at:.2f}: more than 1 per {BROLL_PER_SECONDS:.0f}s of output")
            continue
        d = round(o_end - o_start, 3)
        start = None if shot is None else _shot_start(float(shot), d, spans or [], clip_duration)
        if start is not None and any(start < e and start + d > s for s, e in used):
            notes.append(f"dropped broll {label}: that footage is already shown (kept range or another cutaway); "
                         "use a different shot")
            continue
        out.append(Broll(image, round(at, 3), d, start))
        if start is not None:
            used.append((start, start + d))
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
                 voice_lines: dict | None = None, voice_lookup=None,
                 spans: tuple | list = ()) -> tuple[Edl, list[str]]:
    """`voice_lookup(at, text) -> VoiceLine | None` finds lines not made in this session but already in the voice
    cache (a re-edit reusing the previous EDL's lines): a cache hit counts as generated."""
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
        pos = str(h.get("position") or "middle").strip().lower()
        if pos not in HOOK_POSITIONS:
            raise EdlError(f"hook position must be one of {', '.join(HOOK_POSITIONS)}")
        if h.get("move_to_front"):
            a, b = (float(x) for x in h["move_to_front"])
            if not (0 <= a < b <= clip_duration + 0.01):
                raise EdlError("hook range is outside the clip or inverted")
            a, b = _snap_pad(a, min(b, clip_duration), words, clip_duration)
            hook = Hook(a, b, text, pos)
        else:
            hook = Hook(None, None, text, pos)       # text over the first 2.5 s of whatever plays first

    fixes = [CaptionFix(float(c["at"]), str(c["wrong"]).strip(), str(c["right"]).strip())
             for c in raw.get("caption_fixes") or []]
    emph = [Emphasis(float(e["at"]), str(e["word"]).strip()) for e in raw.get("emphasis") or []]
    if any(not f.wrong or not f.right for f in fixes):
        raise EdlError("caption_fixes need non-empty wrong and right text")
    if any(not e.word for e in emph):
        raise EdlError("emphasis needs a non-empty word")

    if not voiceover_on:    # with voiceover, fixes/emphasis apply to the voiceover words (matched at render)
        notes += resolve_edits(words, fixes, emph)[2]
        kept, head_notes = keep_short_heads(kept, words, clip_duration)
        kept, tail_notes = keep_short_tails(kept, words, clip_duration)
        tail_notes = head_notes + tail_notes
        kept, trim_notes = trim_dangling_end(kept, words, clip_duration)
        trim_notes = tail_notes + trim_notes
        notes += trim_notes + sentence_edge_notes(kept, words)

    broll = _validate_broll(raw.get("broll") or [], kept, hook, list(image_names), notes, list(spans), clip_duration)

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
    if len(spans) > 1 or image_names:      # something to cut away to
        notes += static_notes(edl)
    edl.voiceover = _validate_voiceover(raw.get("voiceover") or [], edl, voice_lines or {}, voice_lookup)
    return edl, notes


def _validate_voiceover(raw: list, edl: Edl, voice_lines: dict, voice_lookup=None) -> list[VoiceCue]:
    """Every cue must be a line made by the `voiceover` tool in this session or already cached; lines must sit inside kept footage,
    not overlap each other and end before the video ends. Returned in output-time order."""
    if not raw:
        return []
    total = edl.output_duration()
    placed: list[tuple[float, float, VoiceCue]] = []
    for c in raw:
        key = voice_key(c["at"], c["text"])
        line = voice_lines.get(key)
        if line is None and voice_lookup is not None:
            line = voice_lookup(*key)
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
