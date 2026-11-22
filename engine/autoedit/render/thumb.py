"""Poster frame of a rendered video, for the app's library grid."""
import json
import sys
from pathlib import Path
from typing import Callable

from autoedit import bins

THUMB_WIDTH = 360
THUMB_NAME = "thumb.jpg"


def make_thumb(video: Path, out: Path) -> bool:
    """Write a JPEG frame of `video` to `out` (t=1 s, or the first frame for very short videos).
    Returns False on any failure; never raises: a missing thumbnail must not fail an edit."""
    tmp = out.with_name(out.stem + ".part.jpg")
    try:
        if not video.is_file():
            return False
        for t in (1.0, 0.0):
            tmp.unlink(missing_ok=True)
            try:
                bins.run([bins.tool_path("ffmpeg"), "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
                          "-frames:v", "1", "-vf", f"scale={THUMB_WIDTH}:-2", "-q:v", "4", str(tmp)])
            except Exception as err:   # noqa: BLE001 — ffmpeg failure at this seek point; try the next one
                print(f"thumb: {err}", file=sys.stderr)
                continue
            if tmp.is_file() and tmp.stat().st_size > 0:
                tmp.replace(out)
                return True
        return False
    except Exception as err:   # noqa: BLE001
        print(f"thumb: {err}", file=sys.stderr)
        return False
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def backfill(root: Path, on_made: Callable[[Path], None]) -> int:
    """Make the missing thumbnail of each project's last run under `root`. Returns how many were made."""
    if not root.is_dir():
        return 0
    made = 0
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            data = json.loads((d / "project.json").read_text(encoding="utf-8"))
            runs = data.get("runs") or []
            n = runs[-1].get("n") if runs else None
        except (OSError, ValueError, AttributeError):
            continue
        if not isinstance(n, int) or isinstance(n, bool):
            continue
        run_dir = d / "runs" / str(n)
        final, thumb = run_dir / "final.mp4", run_dir / THUMB_NAME
        if not final.is_file() or thumb.exists():
            continue
        if make_thumb(final, thumb):
            made += 1
            on_made(d)
    return made
