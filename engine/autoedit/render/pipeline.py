import os
from dataclasses import dataclass, field
from pathlib import Path

from autoedit.edl import TAIL, Edl, Range
from autoedit.fsutil import part_path
from autoedit.prep import Prepared
from autoedit.prep.keyframes import downscale_image, frame_at
from autoedit.project import Project
from autoedit.errors import RenderFailed, VoiceMissing
from autoedit.render.captions import (build_cues, build_voice_cues, caption_band, hide_cues, speech_intervals,
                                      write_ass)
from autoedit.render.compose import CTA_SECONDS, HOOK_SECONDS, compose
from autoedit.render.loudness import loudnorm
from autoedit.render.overlays import cta_card, prepare_logo, text_card
from autoedit.render.qc import QcReport, edit_checks, run_qc
from autoedit.render.seams import refine_edl
from autoedit.render.segments import extract_audio, extract_segment, render_base
from autoedit.voice import eleven
from autoedit.voice.lines import audio_duration


@dataclass
class RenderResult:
    path: Path
    duration: float
    qc: QcReport | None
    needs_review: bool
    checks: list[str] = field(default_factory=list)    # preview only: freeze / pop issues for the agent


def _broll_inputs(prepared: Prepared, project: Project, edl: Edl, work: Path,
                  preview: bool = False) -> list[tuple[Path, float, float]]:
    """(image, output start, output end) per b-roll, mapped from timeline time. Images are re-saved as RGB JPEGs
    (EXIF rotation applied, alpha flattened) so ffmpeg never has to guess the format."""
    known = {i.name: i.path for i in prepared.images} or {n: project.input_dir / n for n in project.images}
    out = []
    for i, b in enumerate(edl.broll):
        span = edl.output_span(b.at, b.dur)
        if span is None:
            continue
        if b.shot is not None:      # video cutaway: cut the shot with the same look and size as the base
            rng = Range(b.shot, min(prepared.info.duration, b.shot + (span[1] - span[0]) + 0.04))
            out.append((extract_segment(prepared.normalized, rng, project.niche, work / f"cut_{i}.mov", preview),
                        span[0], span[1]))
            continue
        if b.image not in known:
            continue
        out.append((downscale_image(known[b.image], work / f"broll_{i}.jpg", max_side=2400), span[0], span[1]))
    return out


def voice_inputs(project: Project, edl: Edl) -> list[tuple[Path, float, float, float, list]]:
    """(file, output start, duration, timeline at, words) per voiceover line. Files come from the TTS cache; a
    missing entry is synthesized again (that may raise a Voice* error: never render without the voiceover)."""
    if not edl.voiceover:
        return []
    if not project.voice_id:
        raise VoiceMissing(eleven.MSG_MISSING)
    out = []
    for c in edl.voiceover:
        start = edl.output_time(c.at)
        if start is None:   # validate_edl rejects this; never render with a line silently missing
            raise RenderFailed(f"Câu lồng tiếng {c.text!r} (at {c.at}) nằm ngoài đoạn được giữ")
        path, words = eleven.tts(c.text, project.voice_id, project.work_dir / "vo")
        out.append((path, start, audio_duration(path), c.at, words))
    return out


def cut_times(ranges) -> list[float]:
    """Output-time boundaries between consecutive ranges."""
    out, t = [], 0.0
    for r in ranges[:-1]:
        t += r.duration
        out.append(round(t, 3))
    return out


def with_tail(ranges: list[Range], spans, duration: float, tail: float = TAIL) -> list[Range]:
    """The last range runs on up to `tail` s of silent picture, never past its clip or into another range."""
    if not ranges:
        return ranges
    last = ranges[-1]
    hi = duration
    for _, a, b in spans or []:
        if a - 1e-6 <= last.start < b:
            hi = min(hi, b)
    for r in ranges[:-1]:
        if r.start >= last.end - 1e-6:
            hi = min(hi, r.start)
    end = min(hi, last.end + tail)
    if end <= last.end + 1e-3:
        return ranges
    return ranges[:-1] + [Range(last.start, round(end, 3), last.reason)]


def cta_seconds(total: float) -> float:
    """CTA_SECONDS, but never more than a quarter of a very short video (its captions hide meanwhile)."""
    return min(CTA_SECONDS, 0.25 * total)


def _muted(ranges: list[Range], spans: list[tuple[float, float]]) -> list[bool]:
    return [any(a - 1e-6 <= r.start < b for a, b in spans) for r in ranges]


def render(prepared: Prepared, project: Project, edl: Edl, out: Path, preview: bool) -> RenderResult:
    work = project.work_dir / ("render_preview" if preview else "render")
    work.mkdir(parents=True, exist_ok=True)
    if not edl.voiceover and not edl.audio:     # voiceover / audio track: the cuts carry no sound to protect
        edl = refine_edl(edl, prepared.normalized, prepared.info.duration)
    voice = voice_inputs(project, edl)
    heard = edl.heard_words(prepared.words)
    if edl.audio:       # picture as cut, silent; one clip's sound plays unbroken under it, then the tail
        ranges = edl.ordered()
        audio_end = edl.audio.duration
        track = extract_audio(prepared.normalized, edl.audio.start, edl.audio.duration, work / "audio_track.wav")
        voice_files = [(track, 0.0)]
        mute: bool | list[bool] = True
    else:
        speech_cut = edl.ordered()
        audio_end = sum(r.duration for r in speech_cut)
        ranges = with_tail(speech_cut, prepared.spans, prepared.info.duration) if not voice else speech_cut
        voice_files = [(p, s) for p, s, _, _, _ in voice]
        mute = bool(voice) or _muted(ranges, edl.muted_spans)
        if voice:
            audio_end = None    # the voiceover may run to the end
    total = sum(r.duration for r in ranges)
    base = render_base(prepared.normalized, ranges, project.niche, work, preview, mute=mute)
    if voice:
        cues = build_voice_cues([(s, at, ws) for _, s, _, at, ws in voice], edl.caption_fixes, edl.emphasis, total)
    else:
        cues = build_cues(edl.speech_ranges() if edl.audio else speech_cut, heard, edl.caption_fixes,
                          edl.emphasis, total)
    cta_s = cta_seconds(total)
    hide = [(max(0.0, total - cta_s), total + 1.0)]       # the CTA corner card replaces the captions
    band = caption_band(project.niche, edl.caption_position)
    if edl.hook and edl.hook.text and (band == "fashion" or (band == "top" and edl.hook.position == "top")):
        hide.append((0.0, HOOK_SECONDS))     # the hook card sits where these captions go
    ass = write_ass(hide_cues(cues, hide), work / "captions.ass", band, edl.caption_size)
    hook = text_card(edl.hook.text, work / "hook.png") if edl.hook and edl.hook.text else None
    logo = prepare_logo(project.logo_path, work / "logo.png") if project.logo_path else None
    cta = cta_card(edl.cta_text, work / "cta.png")
    music = project.music_path if (project.music_path and edl.music_use) else None
    if voice:
        speech = [(max(0.0, s - 0.15), s + d + 0.15) for _, s, d, _, _ in voice]
    else:
        speech = speech_intervals(edl.speech_ranges() if edl.audio else speech_cut, heard)
    broll = _broll_inputs(prepared, project, edl, work, preview)

    def once() -> Path:
        mixed = compose(base, work / "composite.mp4", duration=total, ass=ass, hook_png=hook, logo_png=logo,
                        cta_png=cta, music=music, speech=speech, duck_db=edl.music_duck_db, preview=preview, broll=broll,
                        voice=voice_files,
                        hook_position=edl.hook.position if edl.hook else "middle", audio_end=audio_end,
                        cta_seconds=cta_s)
        tmp = part_path(out)
        try:
            loudnorm(mixed, tmp, two_pass=not preview)
            os.replace(tmp, out)
        finally:
            tmp.unlink(missing_ok=True)
        return out

    once()
    windows = [(a, b) for _, a, b in broll]
    # with voiceover the base is muted and the voice runs across cuts: a pop score on the mix would flag speech
    cuts = [] if (edl.voiceover or edl.audio) else cut_times(ranges)
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
