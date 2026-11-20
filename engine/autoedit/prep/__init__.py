import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from autoedit.events import Emitter
from autoedit.fsutil import atomic_write_text
from autoedit.prep.keyframes import extract_keyframes
from autoedit.prep.normalize import normalize
from autoedit.prep.probe import MediaInfo, check_clip, check_logo, check_music, probe
from autoedit.prep.transcribe import transcribe
from autoedit.project import Project
from autoedit.transcript import Word


@dataclass
class Prepared:
    info: MediaInfo
    normalized: Path
    words: list[Word]
    keyframes: list[Path]


def _fingerprint(norm: Path, clip: Path) -> dict:
    c = clip.stat()
    return {"size": norm.stat().st_size, "clip_size": c.st_size, "clip_mtime_ns": c.st_mtime_ns}


def _cache_valid(norm: Path, clip: Path, src_info: MediaInfo) -> bool:
    """Reuse normalized.mp4 only if its sidecar (written after the atomic replace) matches the file size and the
    exact clip, and it decodes to about the clip's duration. A truncated file never matches."""
    side = norm.with_suffix(".json")
    if not norm.exists() or not side.exists():
        return False
    try:
        if json.loads(side.read_text(encoding="utf-8")) != _fingerprint(norm, clip):
            return False
        return abs(probe(norm).duration - src_info.duration) <= 0.2
    except Exception:
        return False


def prepare(project: Project, events: Emitter) -> Prepared:
    events.step("Đang kiểm tra file…", 0.02)
    src_info = check_clip(project.clip_path)
    if project.logo_path:
        check_logo(project.logo_path)
    if project.music_path:
        check_music(project.music_path)

    norm = project.work_dir / "normalized.mp4"
    if not _cache_valid(norm, project.clip_path, src_info):
        events.step("Đang chuẩn hóa video…", 0.08)
        norm.with_suffix(".json").unlink(missing_ok=True)
        normalize(project.clip_path, norm, src_info)
        atomic_write_text(norm.with_suffix(".json"), json.dumps(_fingerprint(norm, project.clip_path)))
        shutil.rmtree(project.work_dir / "frames", ignore_errors=True)  # keyframes belong to the old render
    info = probe(norm)

    events.step("Đang nghe lời thoại…", 0.15)
    words = transcribe(norm, project.work_dir)

    frames_dir = project.work_dir / "frames"
    frames = sorted(frames_dir.glob("kf_*.jpg"))
    if len(frames) != 6:
        events.step("Đang xem các cảnh…", 0.22)
        frames = extract_keyframes(norm, frames_dir, info.duration, n=6)
    return Prepared(info=info, normalized=norm, words=words, keyframes=frames)
