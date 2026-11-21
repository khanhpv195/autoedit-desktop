import os
from dataclasses import dataclass, field
from pathlib import Path

from autoedit.edl import Edl
from autoedit.fsutil import part_path
from autoedit.prep import Prepared
from autoedit.prep.keyframes import downscale_image, frame_at
from autoedit.project import Project
from autoedit.render.captions import build_cues, speech_intervals, write_ass
from autoedit.render.compose import compose
from autoedit.render.loudness import loudnorm
from autoedit.render.overlays import prepare_logo, text_card
from autoedit.render.qc import QcReport, edit_checks, run_qc
from autoedit.render.segments import render_base


@dataclass
class RenderResult:
    path: Path
    duration: float
    qc: QcReport | None
    needs_review: bool
    checks: list[str] = field(default_factory=list)    # preview only: freeze / pop issues for the agent


def _broll_inputs(prepared: Prepared, project: Project, edl: Edl, work: Path) -> list[tuple[Path, float, float]]:
    """(image, output start, output end) per b-roll, mapped from timeline time. Images are re-saved as RGB JPEGs
    (EXIF rotation applied, alpha flattened) so ffmpeg never has to guess the format."""
    known = {i.name: i.path for i in prepared.images} or {n: project.input_dir / n for n in project.images}
    out = []
    for i, b in enumerate(edl.broll):
        span = edl.output_span(b.at, b.dur)
        if span is None or b.image not in known:
            continue
        out.append((downscale_image(known[b.image], work / f"broll_{i}.jpg", max_side=2400), span[0], span[1]))
    return out


def cut_times(ranges) -> list[float]:
    """Output-time boundaries between consecutive ranges."""
    out, t = [], 0.0
    for r in ranges[:-1]:
        t += r.duration
        out.append(round(t, 3))
    return out


def render(prepared: Prepared, project: Project, edl: Edl, out: Path, preview: bool) -> RenderResult:
    work = project.work_dir / ("render_preview" if preview else "render")
    work.mkdir(parents=True, exist_ok=True)
    ranges = edl.ordered()
    total = sum(r.duration for r in ranges)
    base = render_base(prepared.normalized, ranges, project.niche, work, preview)
    ass = write_ass(build_cues(ranges, prepared.words, edl.caption_fixes, edl.emphasis, total), work / "captions.ass")
    hook = text_card(edl.hook.text, work / "hook.png") if edl.hook and edl.hook.text else None
    logo = prepare_logo(project.logo_path, work / "logo.png") if project.logo_path else None
    cta = text_card(edl.cta_text, work / "cta.png", size=72, bg=(0, 0, 0, 200))
    music = project.music_path if (project.music_path and edl.music_use) else None
    speech = speech_intervals(ranges, prepared.words)
    broll = _broll_inputs(prepared, project, edl, work)

    def once() -> Path:
        mixed = compose(base, work / "composite.mp4", duration=total, ass=ass, hook_png=hook, logo_png=logo,
                        cta_png=cta, music=music, speech=speech, duck_db=edl.music_duck_db, preview=preview, broll=broll)
        tmp = part_path(out)
        try:
            loudnorm(mixed, tmp, two_pass=not preview)
            os.replace(tmp, out)
        finally:
            tmp.unlink(missing_ok=True)
        return out

    once()
    windows = [(a, b) for _, a, b in broll]
    cuts = cut_times(ranges)
    if preview:
        return RenderResult(out, total, None, False, edit_checks(out, windows, cuts))
    qc = run_qc(out, total, broll=windows, cuts=cuts)
    if qc.retryable:
        once()
        qc = run_qc(out, total, broll=windows, cuts=cuts)
    return RenderResult(out, total, qc, not qc.ok)


def preview_frames(video: Path, edl: Edl, out_dir: Path) -> list[Path]:
    times, t = [0.3], 0.0
    for r in edl.ordered()[:-1]:
        t += r.duration
        times.append(t + 0.15)
    return [frame_at(video, x, out_dir / f"pv_{i}.jpg", width=270) for i, x in enumerate(times[:4])]
