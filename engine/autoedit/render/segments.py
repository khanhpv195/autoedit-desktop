"""Hard Rule 2 + 3: per-segment extract with 30ms audio fades, then lossless concat."""
from pathlib import Path

from autoedit import bins
from autoedit.edl import Range
from autoedit.render.look import look_graph

FADE = 0.03


def extract_segment(src: Path, rng: Range, niche: str, out: Path, preview: bool, mute: bool = False) -> Path:
    """mute: the original audio is silenced (voiceover on); the fades stay so the graph is unchanged otherwise."""
    dur = rng.duration
    vgraph = look_graph(niche, "0:v", "v", scale="540:960" if preview else None)
    agraph = f"[0:a]{'volume=0,' if mute else ''}afade=t=in:st=0:d={FADE},afade=t=out:st={max(0.0, dur - FADE):.3f}:d={FADE}[a]"
    preset, crf = ("veryfast", "24") if preview else ("fast", "16")
    bins.run([bins.tool_path("ffmpeg"), "-y", "-v", "error",
              "-ss", f"{rng.start:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
              "-filter_complex", f"{vgraph};{agraph}", "-map", "[v]", "-map", "[a]",
              "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p", "-r", "30",
              "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(out)])
    return out


def extract_audio(src: Path, start: float, dur: float, out: Path) -> Path:
    """One continuous stretch of the timeline's sound (an EDL audio track): 30 ms fade in, END_FADE fade out."""
    from autoedit.edl import END_FADE
    bins.run([bins.tool_path("ffmpeg"), "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src),
              "-t", f"{dur:.3f}", "-vn",
              "-af", f"afade=t=in:st=0:d={FADE},afade=t=out:st={max(0.0, dur - END_FADE):.3f}:d={END_FADE}",
              "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(out)])
    return out


def _quote(path: str) -> str:
    """Concat demuxer: inside '...' only the quote itself needs escaping, as '\\''."""
    return path.replace("'", "'\\''")


def render_base(src: Path, ranges: list[Range], niche: str, work: Path, preview: bool,
                mute: bool | list[bool] = False) -> Path:
    """mute: True silences every range; a list silences range i when mute[i] (a muted clip)."""
    flags = list(mute) if isinstance(mute, (list, tuple)) else [bool(mute)] * len(ranges)
    seg_dir = work / ("segs_preview" if preview else "segs")
    seg_dir.mkdir(parents=True, exist_ok=True)
    for old in seg_dir.glob("seg_*.mov"):
        old.unlink()
    segs = [extract_segment(src, r, niche, seg_dir / f"seg_{i:02d}.mov", preview, flags[i])
            for i, r in enumerate(ranges)]
    lst = seg_dir / "concat.txt"
    lst.write_text("".join(f"file '{_quote(p.resolve().as_posix())}'\n" for p in segs), encoding="utf-8")
    base = work / ("base_preview.mov" if preview else "base.mov")
    bins.run([bins.tool_path("ffmpeg"), "-y", "-v", "error", "-f", "concat", "-safe", "0",
              "-i", str(lst), "-c", "copy", str(base)])
    return base
