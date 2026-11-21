import json
import subprocess
from pathlib import Path

from autoedit import bins

TARGET_I, TARGET_TP, TARGET_LRA = -14.0, -1.5, 11.0   # TP margin: the AAC encode overshoots ~0.2 dB
_BASE = f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"


def measure(path: Path) -> dict | None:
    proc = subprocess.run([bins.tool_path("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path),
                           "-af", f"{_BASE}:print_format=json", "-vn", "-f", "null", "-"],
                          capture_output=True, text=True)
    s, e = proc.stderr.rfind("{"), proc.stderr.rfind("}")
    if s == -1 or e <= s:
        return None
    try:
        data = json.loads(proc.stderr[s:e + 1])
    except json.JSONDecodeError:
        return None
    need = {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}
    return data if need <= data.keys() else None


def loudnorm(src: Path, dst: Path, two_pass: bool) -> Path:
    af = _BASE
    if two_pass and (m := measure(src)):
        af = (f"{_BASE}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
              f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    bins.run([bins.tool_path("ffmpeg"), "-y", "-v", "error", "-i", str(src), "-c:v", "copy", "-af", af,
              "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(dst)])
    return dst
