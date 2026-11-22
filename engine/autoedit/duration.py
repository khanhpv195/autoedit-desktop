"""Target length from the customer's own words ("cắt còn 30s", "khoảng 1 phút", "dưới 40 giây").

A number only counts as a length when a length word stands right before it ("còn", "khoảng", "video", "dưới"...),
so timestamps in the same prompt ("hình clip 1 từ 0 đến 44.2s") are never read as the target. A prompt that is
nothing but a length ("30s", "45-60 giây") counts too.
"""
import re

EXACT_TOL, APPROX_TOL = 0.10, 0.15

_NUM = r"\d+(?:[.,]\d+)?"
_SEC = r"(?:giây|giay|secs?|seconds?|s)(?![\w])"
_MIN = r"(?:phút|phut|mins?|minutes?|p|m(?=\s*\d))(?![^\W\d])"
# 1 phút 30 (giây) | 1p30 | 1m30s | 1 phút rưỡi | 90s | 90 giây | 2 phút
_ONE = (rf"(?:(?P<{{p}}m>{_NUM})\s*{_MIN}\s*(?:(?P<{{p}}ms>\d+)\s*(?:{_SEC})?|(?P<{{p}}half>rưỡi|ruoi))?"
        rf"|(?P<{{p}}s>{_NUM})\s*{_SEC}|(?P<{{p}}nua>nửa|nua)\s*{_MIN})")
_RANGE_SEP = r"\s*(?:-|–|—|đến|tới|toi|den|to)\s*"
# a bare number before a range separator takes the unit of the second number ("30-45s", "1-2 phút")
_RANGE = rf"(?P<lo>{_NUM}){_RANGE_SEP}(?P<hi>{_NUM})\s*(?P<unit>{_MIN}|{_SEC})"

APPROX = r"khoảng|khoang|tầm|tam|chừng|chung|cỡ|co|xấp xỉ|around|about|approx|~"
UNDER = r"dưới|duoi|tối đa|toi da|không quá|khong qua|max|under|at most|ngắn hơn"
OVER = r"trên|tren|ít nhất|it nhat|tối thiểu|toi thieu|at least|min|dài hơn"
OTHER = (r"còn|con|dài|dai|thời lượng|thoi luong|độ dài|do dai|làm|lam|cắt|cat|rút|rut|video|clip|"
         r"length|target|gói gọn|goi gon")
_CUE = rf"(?P<cue>(?:{APPROX}|{UNDER}|{OVER}|{OTHER}))"
# up to two filler words between the cue and the number ("còn khoảng 30s", "video tầm 1 phút")
_LEAD = rf"(?<![\w]){_CUE}(?:\s+(?P<cue2>{APPROX}|{UNDER}|{OVER}))?\s*(?:[:=]\s*)?"

_CUED_RANGE = re.compile(_LEAD + _RANGE, re.I)
_CUED_ONE = re.compile(_LEAD + _ONE.format(p="a_"), re.I)
_BARE_RANGE = re.compile(rf"^\s*{_RANGE}\s*$", re.I)
_BARE_ONE = re.compile(rf"^\s*(?:(?P<cue>{APPROX})\s*)?{_ONE.format(p='a_')}\s*$", re.I)


# "3s đầu", "10 giây cuối": a part of the video, not its length
_SPOT = re.compile(r"\s*(?:đầu|dau|cuối|cuoi|first|last|opening|ending)(?!\w)", re.I)


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _unit_seconds(unit: str) -> float:
    return 1.0 if re.fullmatch(_SEC, unit, re.I) else 60.0


def _one_seconds(m: re.Match) -> float:
    g = m.groupdict()
    if g.get("a_m"):
        sec = _num(g["a_m"]) * 60
        if g.get("a_ms"):
            sec += float(g["a_ms"])
        elif g.get("a_half"):
            sec += 30
        return sec
    if g.get("a_nua"):
        return 30.0
    return _num(g["a_s"])


def _kind(m: re.Match) -> str:
    for cue in (m.groupdict().get("cue2"), m.groupdict().get("cue")):
        if not cue:
            continue
        for kind, words in (("approx", APPROX), ("under", UNDER), ("over", OVER)):
            if re.fullmatch(words, cue, re.I):
                return kind
    return "exact"


def _window(sec: float, kind: str) -> tuple[float, float]:
    if kind == "under":
        return round(sec * 0.6, 1), round(sec, 1)
    if kind == "over":
        return round(sec, 1), round(sec * 1.4, 1)
    tol = APPROX_TOL if kind == "approx" else EXACT_TOL
    return round(sec * (1 - tol), 1), round(sec * (1 + tol), 1)


def _range(m: re.Match) -> tuple[float, float]:
    k = _unit_seconds(m["unit"])
    lo, hi = sorted((_num(m["lo"]) * k, _num(m["hi"]) * k))
    return round(lo, 1), round(hi, 1)


def parse_duration(text: str | None) -> tuple[float, float] | None:
    """(lo, hi) seconds the customer asked for, or None when the text names no length."""
    if not text or not text.strip():
        return None
    t = text.strip()
    m = _BARE_RANGE.match(t)
    if m:
        return _range(m)
    m = _BARE_ONE.match(t)
    if m:
        return _window(_one_seconds(m), _kind(m))
    found = []
    for rx, conv in ((_CUED_RANGE, lambda m: _range(m)), (_CUED_ONE, lambda m: _window(_one_seconds(m), _kind(m)))):
        for m in rx.finditer(t):
            if not _SPOT.match(t, m.end()):
                found.append((m.start(), conv(m)))
    if not found:
        return None
    lo, hi = min(found)[1]
    return (lo, hi) if 0 < hi <= 600 else None
