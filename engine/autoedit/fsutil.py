"""Atomic file writes: write a sibling temp file, then os.replace, so a kill never leaves a half-written file."""
import os
from pathlib import Path


def part_path(p: Path) -> Path:
    """Sibling temp name that keeps the extension (ffmpeg infers the container from it)."""
    return p.with_name(f"{p.stem}.part{p.suffix}")


def atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.part")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
