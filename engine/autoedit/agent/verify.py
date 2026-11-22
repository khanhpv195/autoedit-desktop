"""transcribe_output: listen to the rendered preview again and check that what should be heard is heard. The
expected words are the last heard word of every speech range (in play order) and the video's last word; each must
be found in the output's own transcript near the output time the EDL puts it at."""
import difflib
import re

from autoedit.edl import Edl
from autoedit.render.captions import map_words
from autoedit.transcript import Word

TOLERANCE = 1.2         # s: the output transcript's times vs the EDL's mapped times
SIMILAR = 0.6


def _norm(t: str) -> str:
    return re.sub(r"[^\w]+", "", t.casefold())


def expected_words(edl: Edl, words: list[Word]) -> list[dict]:
    """[{text, at (output s), what}] in output order."""
    ranges = edl.speech_ranges()
    mapped = map_words(ranges, edl.heard_words(words), [], [])
    out, t = [], 0.0
    for i, r in enumerate(ranges):
        inside = [w for w in mapped if t - 1e-6 <= w.start < t + r.duration - 1e-6]
        if inside:
            w = inside[-1]
            out.append({"text": w.text, "at": round(w.start, 2), "what": f"last word of part {i + 1}"})
        t += r.duration
    if mapped:
        last = mapped[-1]
        if not out or out[-1]["at"] != round(last.start, 2):
            out.append({"text": last.text, "at": round(last.start, 2), "what": "last word of the video"})
        else:
            out[-1]["what"] += " (the video's last word)"
    return out


def _matches(want: str, heard: list[Word], i: int) -> bool:
    w = _norm(want)
    if not w:
        return True
    cands = [_norm(heard[i].text)]
    if i + 1 < len(heard):
        cands.append(cands[0] + _norm(heard[i + 1].text))      # whisper may split or join a word differently
    return any(c == w or (c and difflib.SequenceMatcher(None, c, w).ratio() >= SIMILAR) for c in cands)


def check_output(expected: list[dict], heard: list[Word], tol: float = TOLERANCE) -> list[dict]:
    """The expected words not found in `heard` (output transcript) within ±tol of their time."""
    missing = []
    for e in expected:
        near = [i for i, h in enumerate(heard) if abs(h.start - e["at"]) <= tol or abs(h.end - e["at"]) <= tol]
        if not any(_matches(e["text"], heard, i) for i in near):
            around = " ".join(heard[i].text for i in near) or "(nothing heard)"
            missing.append({**e, "heard_around": around})
    return missing
