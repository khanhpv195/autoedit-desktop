import re
import statistics
import subprocess
from array import array
from dataclasses import dataclass, field
from pathlib import Path

from autoedit import bins
from autoedit.prep.probe import probe
from autoedit.render.loudness import TARGET_I, measure


@dataclass
class QcReport:
    ok: bool
    issues: list[str] = field(default_factory=list)
    duration: float = 0.0
    lufs: float | None = None
    retryable: bool = False     # a re-render might fix it


FREEZE_NOISE, FREEZE_MIN = 0.003, 0.5
POP_NEAR, POP_CTX = 0.015, 0.3      # seconds either side of a cut
POP_MAX = 8.0
POP_MIN_JUMP = 0.05     # a "pop" quieter than this is inaudible; avoids huge ratios at a cut into near-silence


def detect_freezes(path: Path, noise: float = FREEZE_NOISE, min_dur: float = FREEZE_MIN) -> list[tuple[float, float]]:
    """(start, end) of held/frozen video stretches, from ffmpeg freezedetect (ported from pixel-video-edit's
    freeze_check.py). A freeze that runs to the end of the file has no freeze_end: it ends at the duration."""
    proc = subprocess.run([bins.tool_path("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path),
                           "-vf", f"freezedetect=n={noise}:d={min_dur}", "-an", "-f", "null", "-"],
                          capture_output=True, text=True)
    err = proc.stderr or ""
    starts = [float(x) for x in re.findall(r"freeze_start:\s*([0-9.]+)", err)]
    ends = [float(x) for x in re.findall(r"freeze_end:\s*([0-9.]+)", err)]
    if len(ends) < len(starts):
        ends.append(probe(path).duration)
    return [(round(a, 3), round(b, 3)) for a, b in zip(starts, ends)]


def _pcm(path: Path, sr: int) -> array:
    proc = subprocess.run([bins.tool_path("ffmpeg"), "-v", "error", "-i", str(path), "-vn", "-ac", "1",
                           "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
    x = array("f")
    x.frombytes(proc.stdout[: len(proc.stdout) // 4 * 4])
    return x


def _pop_at(x: array, cut: float, sr: int) -> tuple[float, float]:
    """(largest sample-to-sample jump within ±15 ms of the cut, median jump within ±300 ms)."""
    i, n, m = int(cut * sr), int(POP_NEAR * sr), int(POP_CTX * sr)
    lo, hi = max(1, i - m), min(len(x), i + m)
    if hi - lo < 2:
        return 0.0, 0.0
    d = [abs(x[k] - x[k - 1]) for k in range(lo, hi)]
    near = d[max(0, i - n - lo): max(0, i + n - lo)] or [0.0]
    return max(near), statistics.median(d)


def pop_scores(path: Path, cuts: list[float], sr: int = 48000) -> list[tuple[float, float]]:
    """(cut_t, score) per cut: max jump near the cut / (median jump around it + 1e-6). Ported from
    pixel-video-edit's self_eval.py. Above 8 is an audible click."""
    if not cuts:
        return []
    x = _pcm(path, sr)
    return [(c, near / (ctx + 1e-6)) for c in cuts for near, ctx in [_pop_at(x, c, sr)]]


def edit_checks(path: Path, broll=(), cuts=(), video: bool = True, sr: int = 48000) -> list[str]:
    """Freeze + pop checks (Vietnamese issue strings). Freezes inside a b-roll window are fine (stills)."""
    issues: list[str] = []
    if video:
        for s, e in detect_freezes(path):
            if not any(s < be and e > bs for bs, be in broll):
                issues.append(f"khung đứng {s:.2f}–{e:.2f}s")
    cuts = list(cuts)
    if cuts:
        x = _pcm(path, sr)
        for c in cuts:
            near, ctx = _pop_at(x, c, sr)
            if near >= POP_MIN_JUMP and near / (ctx + 1e-6) > POP_MAX:
                issues.append(f"tiếng bụp ở cắt {c:.2f}s")
    return issues


def run_qc(path: Path, expected_duration: float, *, broll=(), cuts=()) -> QcReport:
    issues: list[str] = []
    dur = probe(path).duration
    if abs(dur - expected_duration) > 0.1:
        issues.append(f"thời lượng {dur:.2f}s khác dự kiến {expected_duration:.2f}s")
    m = measure(path)
    lufs = float(m["input_i"]) if m else None
    if lufs is None or abs(lufs - TARGET_I) > 1.0:
        issues.append(f"độ to {lufs} LUFS, cần {TARGET_I}±1")
    proc = subprocess.run([bins.tool_path("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path),
                           "-vf", "blackdetect=d=0.5:pix_th=0.10", "-an", "-f", "null", "-"],
                          capture_output=True, text=True)
    blacks = re.findall(r"black_start:([\d.]+)", proc.stderr)
    if blacks:
        issues.append(f"có khung đen > 0.5s tại {', '.join(blacks)}s")
    retryable = bool(issues)        # duration / loudness / black frames may be a bad encode; freezes and pops are not
    issues += edit_checks(path, broll, cuts)
    return QcReport(ok=not issues, issues=issues, duration=dur, lufs=lufs, retryable=retryable)
