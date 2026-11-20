from dataclasses import asdict, dataclass, field

from autoedit.transcript import Word, speech_duration

PAD_BEFORE = 0.05
PAD_AFTER = 0.08
MIN_SEGMENT = 0.4
MIN_KEEP_RATIO = 0.30
HOOK_MAX_WORDS = 5
DEFAULT_CTA = "BẤM GIỎ HÀNG 👇"


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
    start: float
    end: float
    text: str


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
class Edl:
    keep: list[Range]
    hook: Hook | None = None
    caption_fixes: list[CaptionFix] = field(default_factory=list)
    emphasis: list[Emphasis] = field(default_factory=list)
    cta_text: str = DEFAULT_CTA
    music_use: bool = True
    music_duck_db: float = -14.0

    def to_dict(self) -> dict:
        return {
            "keep": [asdict(r) for r in self.keep],
            "hook": {"move_to_front": [self.hook.start, self.hook.end], "text": self.hook.text} if self.hook else None,
            "caption_fixes": [asdict(c) for c in self.caption_fixes],
            "emphasis": [asdict(e) for e in self.emphasis],
            "cta_text": self.cta_text,
            "music": {"use": self.music_use, "duck_db": self.music_duck_db},
        }

    def ordered(self) -> list[Range]:
        if not self.hook:
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

    def output_duration(self) -> float:
        return sum(r.duration for r in self.ordered())


def _snap_pad(a: float, b: float, words: list[Word], dur: float) -> tuple[float, float]:
    """Snap to word edges and pad. A range with no words (silent scene) keeps its edges unpadded."""
    inside = [w for w in words if w.end > a and w.start < b]
    if not inside:
        return a, b
    return max(0.0, inside[0].start - PAD_BEFORE), min(dur, inside[-1].end + PAD_AFTER)


def _speech_in(ranges: list[Range], words: list[Word]) -> float:
    total = 0.0
    for w in words:
        for r in ranges:
            total += max(0.0, min(w.end, r.end) - max(w.start, r.start))
    return total


def validate_edl(raw: dict, words: list[Word], clip_duration: float) -> tuple[Edl, list[str]]:
    notes: list[str] = []
    keep_raw = raw.get("keep") or []
    if not keep_raw:
        raise EdlError("keep must contain at least one range")
    ranges: list[Range] = []
    for k in keep_raw:
        a, b = float(k["start"]), float(k["end"])
        if not (0 <= a < b <= clip_duration + 0.01):
            raise EdlError(f"range {a}-{b} is outside 0-{clip_duration:.2f} or inverted")
        a, b = _snap_pad(a, min(b, clip_duration), words, clip_duration)
        ranges.append(Range(a, b, str(k.get("reason", ""))))

    ranges.sort(key=lambda r: r.start)
    merged: list[Range] = []
    for r in ranges:
        if merged and r.start <= merged[-1].end:
            merged[-1].end = max(merged[-1].end, r.end)
        else:
            merged.append(r)
    kept = []
    for r in merged:
        if r.duration < MIN_SEGMENT:
            notes.append(f"dropped {r.start:.2f}-{r.end:.2f}: shorter than {MIN_SEGMENT}s")
        else:
            kept.append(r)
    if not kept:
        raise EdlError("every range is shorter than 0.4s")

    total_speech = speech_duration(words)
    if total_speech > 0:
        ratio = _speech_in(kept, words) / total_speech
        if ratio < MIN_KEEP_RATIO:
            raise EdlError(f"keeps only {ratio:.0%} of the speech; keep at least 30%")

    hook = None
    if raw.get("hook"):
        h = raw["hook"]
        text = str(h.get("text", "")).strip()
        if len(text.split()) > HOOK_MAX_WORDS:
            raise EdlError(f"hook text must be at most {HOOK_MAX_WORDS} words")
        a, b = (float(x) for x in h["move_to_front"])
        if not (0 <= a < b <= clip_duration + 0.01):
            raise EdlError("hook range is outside the clip or inverted")
        a, b = _snap_pad(a, min(b, clip_duration), words, clip_duration)
        hook = Hook(a, b, text)

    music = raw.get("music") or {}
    duck = float(music.get("duck_db", -14.0))
    edl = Edl(
        keep=kept,
        hook=hook,
        caption_fixes=[CaptionFix(float(c["at"]), str(c["wrong"]), str(c["right"])) for c in raw.get("caption_fixes") or []],
        emphasis=[Emphasis(float(e["at"]), str(e["word"])) for e in raw.get("emphasis") or []],
        cta_text=(raw.get("cta_text") or "").strip() or DEFAULT_CTA,
        music_use=bool(music.get("use", True)),
        music_duck_db=min(-6.0, max(-24.0, duck)),
    )
    return edl, notes
