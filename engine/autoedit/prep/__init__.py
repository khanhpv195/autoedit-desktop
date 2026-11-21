import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from autoedit.events import Emitter
from autoedit.fsutil import atomic_write_text
from autoedit.prep.keyframes import downscale_image, extract_keyframes
from autoedit.prep.normalize import concat, normalize
from autoedit.prep.probe import (MediaInfo, check_clip, check_image, check_logo, check_music,
                                 check_total_duration, probe)
from autoedit.prep.transcribe import transcribe
from autoedit.project import Project
from autoedit.transcript import Word


@dataclass
class PreparedImage:
    name: str           # file name inside input/ (what the EDL's broll.image refers to)
    path: Path          # original file (rendered full-frame)
    small: Path         # downscaled JPEG shown to the agent
    width: int
    height: int


@dataclass
class Prepared:
    info: MediaInfo
    normalized: Path    # the timeline: all clips normalized and joined in order
    words: list[Word]
    keyframes: list[Path]
    spans: list[tuple[str, float, float]] = field(default_factory=list)   # (clip name, start, end) in timeline s
    images: list[PreparedImage] = field(default_factory=list)

    @property
    def timeline(self) -> Path:
        return self.normalized

    @property
    def image_names(self) -> list[str]:
        return [i.name for i in self.images]


def _fingerprint(norm: Path, clip: Path) -> dict:
    c = clip.stat()
    return {"size": norm.stat().st_size, "clip_size": c.st_size, "clip_mtime_ns": c.st_mtime_ns}


def _cache_valid(norm: Path, clip: Path, src_info: MediaInfo) -> bool:
    """Reuse a normalized clip only if its sidecar (written after the atomic replace) matches the file size and the
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


def _norm_name(i: int, clip: Path) -> str:
    return f"{i}_{re.sub(r'[^A-Za-z0-9._-]+', '_', clip.stem)[:40]}.mp4"


def _concat_fingerprint(parts: list[Path]) -> list[dict]:
    return [{"name": p.name, "size": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns} for p in parts]


def _build_timeline(project: Project, events: Emitter, clips: list[Path],
                    infos: list[MediaInfo]) -> tuple[Path, str, list[Path]]:
    """Normalize each clip (cached per clip), join them. Returns (timeline file, fingerprint, normalized parts)."""
    norm_dir = project.work_dir / "norm"
    parts: list[Path] = []
    for i, (clip, info) in enumerate(zip(clips, infos)):
        norm = norm_dir / _norm_name(i, clip)
        if not _cache_valid(norm, clip, info):
            events.step("Đang chuẩn hóa video…" if len(clips) == 1 else f"Đang chuẩn hóa clip {i + 1}/{len(clips)}…",
                        0.08)
            norm.with_suffix(".json").unlink(missing_ok=True)
            normalize(clip, norm, info)
            atomic_write_text(norm.with_suffix(".json"), json.dumps(_fingerprint(norm, clip)))
        parts.append(norm)
    # drop normalized files of clips that are no longer in the project
    keep = {p.name for p in parts} | {p.with_suffix(".json").name for p in parts}
    for old in norm_dir.glob("*"):
        if old.name not in keep:
            old.unlink(missing_ok=True)
    fp = json.dumps(_concat_fingerprint(parts), sort_keys=True)
    if len(parts) == 1:
        return parts[0], fp, parts
    source = project.work_dir / "source.mp4"
    side = source.with_suffix(".json")
    total = sum(probe(p).duration for p in parts)
    try:
        valid = (source.exists() and side.exists() and json.loads(side.read_text(encoding="utf-8")) == fp
                 and abs(probe(source).duration - total) <= 0.3)
    except Exception:
        valid = False
    if not valid:
        events.step("Đang ghép các clip…", 0.12)
        side.unlink(missing_ok=True)
        concat(parts, source)
        atomic_write_text(side, json.dumps(fp))
    return source, fp, parts


def _spans(clips: list[Path], parts_duration: list[float]) -> list[tuple[str, float, float]]:
    spans, t = [], 0.0
    for clip, d in zip(clips, parts_duration):
        spans.append((clip.name, round(t, 3), round(t + d, 3)))
        t += d
    return spans


def _prepare_images(project: Project) -> list[PreparedImage]:
    out = []
    for i, path in enumerate(project.image_paths):
        w, h = check_image(path)
        small = project.work_dir / "images" / f"{i}_{re.sub(r'[^A-Za-z0-9._-]+', '_', path.stem)[:40]}.jpg"
        if not small.exists() or small.stat().st_mtime < path.stat().st_mtime:
            downscale_image(path, small)
        out.append(PreparedImage(project.images[i], path, small, w, h))
    keep = {i.small.name for i in out}
    for old in (project.work_dir / "images").glob("*.jpg"):
        if old.name not in keep:
            old.unlink(missing_ok=True)
    return out


def prepare(project: Project, events: Emitter) -> Prepared:
    events.step("Đang kiểm tra file…", 0.02)
    clips = project.clip_paths
    infos = [check_clip(c) for c in clips]
    check_total_duration(sum(i.duration for i in infos))
    if project.logo_path:
        check_logo(project.logo_path)
    if project.music_path:
        check_music(project.music_path)
    images = _prepare_images(project)

    timeline, fp, parts = _build_timeline(project, events, clips, infos)
    info = probe(timeline)
    part_durations = [probe(p).duration for p in parts]
    spans = _spans(clips, part_durations)
    if spans:    # the joined file is a hair off the sum of its parts; the last clip absorbs the difference
        n, a, _ = spans[-1]
        spans[-1] = (n, a, round(max(a, info.duration), 3))

    events.step("Đang nghe lời thoại…", 0.15)
    words = transcribe(timeline, project.work_dir)

    n_frames = max(6, min(12, 2 * len(clips)))
    frames_dir = project.work_dir / "frames"
    stamp = frames_dir / "timeline.json"
    if not stamp.exists() or stamp.read_text(encoding="utf-8") != fp:
        shutil.rmtree(frames_dir, ignore_errors=True)       # keyframes belong to an older timeline
    frames = sorted(frames_dir.glob("kf_*.jpg"), key=lambda p: int(p.stem.split("_")[1]))
    if len(frames) != n_frames:
        events.step("Đang xem các cảnh…", 0.22)
        shutil.rmtree(frames_dir, ignore_errors=True)
        frames = extract_keyframes(timeline, frames_dir, info.duration, n=n_frames)
        atomic_write_text(stamp, fp)
    return Prepared(info=info, normalized=timeline, words=words, keyframes=frames, spans=spans, images=images)
