import shutil
from dataclasses import dataclass
from pathlib import Path

from autoedit.events import Emitter
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


def prepare(project: Project, events: Emitter) -> Prepared:
    events.step("Đang kiểm tra file…", 0.02)
    src_info = check_clip(project.clip_path)
    if project.logo_path:
        check_logo(project.logo_path)
    if project.music_path:
        check_music(project.music_path)

    norm = project.work_dir / "normalized.mp4"
    if not norm.exists() or norm.stat().st_mtime < project.clip_path.stat().st_mtime:
        events.step("Đang chuẩn hóa video…", 0.08)
        normalize(project.clip_path, norm, src_info)
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
