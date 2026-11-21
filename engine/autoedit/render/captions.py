"""Vietnamese captions on the OUTPUT timeline (Hard Rule 5), chunked per edit-video rules."""
import re
from dataclasses import dataclass
from pathlib import Path

from autoedit.edl import CaptionFix, Emphasis, Range
from autoedit.transcript import Word, resolve_edits

FONT_NAME = "Be Vietnam Pro ExtraBold"
LEAD = {"các", "cực", "rất", "như", "một", "của", "cho", "mà", "có", "nhìn", "biết", "tất", "đến", "với",
        "là", "mọi", "nhà", "chiếc", "cái", "em", "những", "và", "thì", "để", "vì", "nên", "đã"}
GLUE = {"ơi", "yêu", "ứng", "kỳ", "ạ", "nha", "nhá", "í", "nhé", "luôn"}
PUNCT = ".,?!;:"


@dataclass
class TimedWord:
    text: str
    start: float
    end: float
    src_start: float
    group: int
    emph: bool = False


@dataclass
class Cue:
    start: float
    end: float
    words: list[TimedWord]


def _offsets(ranges: list[Range]) -> tuple[list[float], list[int]]:
    offs, off = [], 0.0
    for r in ranges:
        offs.append(off)
        off += r.duration
    groups = [0]
    for i in range(1, len(ranges)):
        jump = ranges[i].start - ranges[i - 1].end
        groups.append(groups[-1] + (1 if jump < 0 or jump > 2.0 else 0))
    return offs, groups


def map_words(ranges: list[Range], words: list[Word], fixes: list[CaptionFix],
              emphasis: list[Emphasis]) -> list[TimedWord]:
    offs, groups = _offsets(ranges)
    out: list[TimedWord] = []
    fixed, emph_idx, _ = resolve_edits(words, fixes, emphasis)
    for k, w in enumerate(fixed):
        best, best_ov = -1, 0.0
        for i, r in enumerate(ranges):
            ov = min(w.end, r.end) - max(w.start, r.start)
            if ov > best_ov:
                best, best_ov = i, ov
        if best < 0:
            continue
        r = ranges[best]
        out.append(TimedWord(w.text, max(r.start, w.start) - r.start + offs[best],
                             min(r.end, w.end) - r.start + offs[best], w.start, groups[best], k in emph_idx))
    out.sort(key=lambda t: t.start)
    return out


def chunk(ws: list[TimedWord], target: int = 4, hard: int = 6) -> list[list[TimedWord]]:
    chunks: list[list[TimedWord]] = []
    cur: list[TimedWord] = []
    for i, w in enumerate(ws):
        nx = ws[i + 1] if i + 1 < len(ws) else None
        cur.append(w)
        if nx is None:
            break
        gap = nx.start - w.end
        core = w.text.rstrip(PUNCT).lower()
        if nx.text.rstrip(PUNCT).lower() in GLUE and len(cur) < hard:
            continue
        if ((w.text[-1] in PUNCT or gap >= 0.3) and len(cur) >= 2) or len(cur) >= hard:
            chunks.append(cur)
            cur = []
        elif len(cur) >= target and core not in LEAD and nx.text[-1] not in PUNCT:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    out: list[list[TimedWord]] = []
    for c in chunks:  # fold single-word orphans into the previous cue
        if len(c) == 1 and out and len(out[-1]) < hard:
            out[-1] = out[-1] + c
        else:
            out.append(c)
    return out


def build_cues(ranges: list[Range], words: list[Word], fixes: list[CaptionFix],
               emphasis: list[Emphasis], total: float) -> list[Cue]:
    return _cues(map_words(ranges, words, fixes, emphasis), total)


def build_voice_cues(lines: list[tuple[float, float, list]], fixes: list[CaptionFix], emphasis: list[Emphasis],
                     total: float) -> list[Cue]:
    """Captions from voiceover words. lines = [(output start, timeline `at`, [(text, start, end) relative to the
    line])]. caption_fixes / emphasis match by text, each line on its own (their `at` is a timeline second, so the
    words are matched at `at + word time`); each line is its own caption group."""
    tw: list[TimedWord] = []
    for g, (out_start, at, words) in enumerate(lines):
        timeline = [Word(str(t), at + float(a), at + float(b)) for t, a, b in words]
        fixed, emph_idx, _ = resolve_edits(timeline, fixes, emphasis)
        for k, w in enumerate(fixed):
            tw.append(TimedWord(w.text, out_start + (w.start - at), out_start + (w.end - at), w.start, g,
                                k in emph_idx))
    tw.sort(key=lambda t: t.start)
    return _cues(tw, total)


def _cues(tw: list[TimedWord], total: float) -> list[Cue]:
    groups: list[list[TimedWord]] = []
    for w in tw:
        if not groups or groups[-1][-1].group != w.group:
            groups.append([])
        groups[-1].append(w)
    cues = [Cue(c[0].start, max(c[-1].end, c[0].start + 0.3), c) for g in groups for c in chunk(g)]
    cues.sort(key=lambda c: c.start)
    for a, b in zip(cues, cues[1:]):
        a.end = min(a.end, b.start)
    if cues:
        cues[-1].end = max(cues[-1].end, total - 0.05)
    return cues


def speech_intervals(ranges: list[Range], words: list[Word], pad: float = 0.15) -> list[tuple[float, float]]:
    iv: list[list[float]] = []
    for w in map_words(ranges, words, [], []):
        a, b = max(0.0, w.start - pad), w.end + pad
        if iv and a - iv[-1][1] < 0.5:
            iv[-1][1] = max(iv[-1][1], b)
        else:
            iv.append([a, b])
    return [(a, b) for a, b in iv]


def _ts(t: float) -> str:
    cs = int(round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def write_ass(cues: list[Cue], path: Path) -> Path:
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Caption,{FONT_NAME},78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,5,0,2,"
        "90,150,540,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = []
    for c in cues:
        parts = []
        for w in c.words:
            t = re.sub(r"[{}\\]", "", w.text).rstrip(",;:.").upper()
            parts.append(f"{{\\c&H0000D7FF&}}{t}{{\\c&H00FFFFFF&}}" if w.emph else t)
        lines.append(f"Dialogue: 0,{_ts(c.start)},{_ts(c.end)},Caption,,0,0,0,,{' '.join(parts)}")
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return path
