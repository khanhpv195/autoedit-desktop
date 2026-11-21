"""Move each cut edge to the quietest moment nearby. Whisper word times run early and Vietnamese speech often has no
gap between words, so a word-snapped edge can clip the last syllable ("ra thôi" -> "ra th-"). The audio knows better."""
import math
from array import array
from dataclasses import replace

from autoedit.edl import Edl, Hook, Range
from autoedit.render.qc import _pcm

SR = 16000
WIN = 0.02          # RMS window
HOP = 0.005
START_SEARCH = (-0.10, 0.03)    # a start may move a little earlier (catch the onset), barely later
END_SEARCH = (-0.03, 0.12)      # an end mostly later: whisper ends words early
LOUD_DB = -32.0                 # still this loud at the best point: the edge sits inside speech, look wider
WIDE_START = (-0.25, 0.06)
WIDE_END = (-0.10, 0.20)


def _rms_db(x: array, t: float) -> float:
    i, n = int(t * SR), int(WIN * SR)
    seg = x[max(0, i - n // 2): i + n // 2]
    if not seg:
        return 0.0
    return 20 * math.log10(math.sqrt(sum(v * v for v in seg) / len(seg)) + 1e-9)


def quietest(x: array, lo: float, hi: float, prefer: float) -> float:
    """Time in [lo, hi] with the lowest RMS; ties (within 1 dB) go to the point nearest `prefer`."""
    best, best_db = prefer, None
    steps = max(0, int((hi - lo) / HOP))
    cands = [(lo + k * HOP, _rms_db(x, lo + k * HOP)) for k in range(steps + 1)]
    if not cands:
        return prefer
    floor = min(db for _, db in cands)
    best = min((t for t, db in cands if db <= floor + 1.0), key=lambda t: abs(t - prefer))
    return round(best, 3)


def refine_ranges(x: array, ranges: list[Range], duration: float) -> list[Range]:
    out = []
    for r in ranges:
        others = [o for o in ranges if o is not r]
        lo_start = max([0.0] + [o.end for o in others if o.end <= r.start + 1e-6])
        hi_end = min([duration] + [o.start for o in others if o.start >= r.end - 1e-6])
        s = quietest(x, max(lo_start, r.start + START_SEARCH[0]), r.start + START_SEARCH[1], r.start)
        if _rms_db(x, s) > LOUD_DB:
            w = quietest(x, max(lo_start, r.start + WIDE_START[0]), r.start + WIDE_START[1], r.start)
            s = w if _rms_db(x, w) < _rms_db(x, s) - 6 else s
        e = quietest(x, r.end + END_SEARCH[0], min(hi_end, r.end + END_SEARCH[1]), r.end)
        if _rms_db(x, e) > LOUD_DB:
            w = quietest(x, r.end + WIDE_END[0], min(hi_end, r.end + WIDE_END[1]), r.end)
            e = w if _rms_db(x, w) < _rms_db(x, e) - 6 else e
        out.append(replace(r, start=s, end=e) if e - s > 0.2 else r)
    return out


def refine_edl(edl: Edl, src, duration: float) -> Edl:
    """Copy of `edl` in play order whose edges sit in the quietest nearby audio (a moved hook becomes the first
    range; its text still covers the first seconds). B-roll, captions and voiceover map through the refined ranges
    since all of them use timeline seconds."""
    x = _pcm(src, SR)
    if not x:
        return edl
    hook = Hook(None, None, edl.hook.text, edl.hook.position) if edl.hook else None
    return replace(edl, keep=refine_ranges(x, edl.ordered(), duration), hook=hook)
