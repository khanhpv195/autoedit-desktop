import re
import subprocess
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


def run_qc(path: Path, expected_duration: float) -> QcReport:
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
    return QcReport(ok=not issues, issues=issues, duration=dur, lufs=lufs)
