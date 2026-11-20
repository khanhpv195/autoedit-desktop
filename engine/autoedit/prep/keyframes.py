from pathlib import Path

from autoedit import bins


def frame_at(video: Path, t: float, out: Path, width: int = 540) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    bins.run([bins.tool_path("ffmpeg"), "-y", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(video),
              "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", str(out)])
    return out


def extract_keyframes(video: Path, out_dir: Path, duration: float, n: int = 6) -> list[Path]:
    return [frame_at(video, duration * (i + 0.5) / n, out_dir / f"kf_{i}.jpg") for i in range(n)]
