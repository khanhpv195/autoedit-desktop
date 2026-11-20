import os
from dataclasses import dataclass
from pathlib import Path

from autoedit.edl import Edl
from autoedit.fsutil import part_path
from autoedit.prep import Prepared
from autoedit.prep.keyframes import frame_at
from autoedit.project import Project
from autoedit.render.captions import build_cues, speech_intervals, write_ass
from autoedit.render.compose import compose
from autoedit.render.loudness import loudnorm
from autoedit.render.overlays import prepare_logo, text_card
from autoedit.render.qc import QcReport, run_qc
from autoedit.render.segments import render_base


@dataclass
class RenderResult:
    path: Path
    duration: float
    qc: QcReport | None
    needs_review: bool


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

    def once() -> Path:
        mixed = compose(base, work / "composite.mp4", duration=total, ass=ass, hook_png=hook, logo_png=logo,
                        cta_png=cta, music=music, speech=speech, duck_db=edl.music_duck_db, preview=preview)
        tmp = part_path(out)
        try:
            loudnorm(mixed, tmp, two_pass=not preview)
            os.replace(tmp, out)
        finally:
            tmp.unlink(missing_ok=True)
        return out

    once()
    if preview:
        return RenderResult(out, total, None, False)
    qc = run_qc(out, total)
    if not qc.ok:
        once()
        qc = run_qc(out, total)
    return RenderResult(out, total, qc, not qc.ok)


def preview_frames(video: Path, edl: Edl, out_dir: Path) -> list[Path]:
    times, t = [0.3], 0.0
    for r in edl.ordered()[:-1]:
        t += r.duration
        times.append(t + 0.15)
    return [frame_at(video, x, out_dir / f"pv_{i}.jpg", width=270) for i, x in enumerate(times[:4])]
