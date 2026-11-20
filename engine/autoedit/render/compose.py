"""Final pass: base -> hook -> logo -> CTA -> subtitles LAST (Hard Rule 1); music ducked under speech."""
import re
from pathlib import Path, PurePath

from autoedit import bins
from autoedit.resources import assets_dir

HOOK_SECONDS = 2.5
CTA_SECONDS = 2.0


def filter_path(p: PurePath) -> str:
    """Escape a path for use as an unquoted filter option value, at both ffmpeg levels:
    option level (backslash, colon, apostrophe), then filtergraph level (backslash, quote, brackets, comma, semicolon)."""
    s = str(p).replace("\\", "/")
    s = s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return re.sub(r"([\\'\[\],;])", r"\\\1", s)


def music_volume_expr(intervals: list[tuple[float, float]], duck_db: float, base_db: float = -8.0) -> str:
    base = 10 ** (base_db / 20)
    duck = 10 ** (duck_db / 20)
    if not intervals:
        return f"{base:.3f}"
    speech = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in intervals)
    return f"{base:.3f}*if(gt({speech},0),{duck:.3f},1)"


def compose(base: Path, out: Path, *, duration: float, ass: Path, hook_png: Path | None,
            logo_png: Path | None, cta_png: Path | None, music: Path | None,
            speech: list[tuple[float, float]], duck_db: float, preview: bool) -> Path:
    k = 0.5 if preview else 1.0
    cmd = [bins.tool_path("ffmpeg"), "-y", "-v", "error", "-i", str(base)]
    graph: list[str] = []
    cur, idx = "0:v", 1

    def add_overlay(png: Path, x: str, y: int, enable: str | None):
        nonlocal cur, idx
        cmd.extend(["-i", str(png)])
        src = f"{idx}:v"
        if preview:
            graph.append(f"[{src}]scale=iw*{k}:ih*{k}[ov{idx}]")
            src = f"ov{idx}"
        en = f":enable='{enable}'" if enable else ""
        graph.append(f"[{cur}][{src}]overlay=x={x}:y={int(y * k)}{en}[v{idx}]")
        cur, idx = f"v{idx}", idx + 1

    if hook_png:
        add_overlay(hook_png, "(W-w)/2", 300, f"between(t,0,{HOOK_SECONDS})")
    if logo_png:
        add_overlay(logo_png, str(int(48 * k)), 120, None)
    if cta_png:
        add_overlay(cta_png, "(W-w)/2", 1000, f"gte(t,{max(0.0, duration - CTA_SECONDS):.3f})")
    fonts = filter_path(assets_dir() / "fonts")
    graph.append(f"[{cur}]subtitles=filename={filter_path(ass)}:fontsdir={fonts}"
                 f"{':original_size=1080x1920' if preview else ''}[vout]")

    if music:
        cmd.extend(["-stream_loop", "-1", "-i", str(music)])
        graph.append(f"[{idx}:a]aresample=48000,volume='{music_volume_expr(speech, duck_db)}':eval=frame,"
                     f"afade=t=out:st={max(0.0, duration - 1):.3f}:d=1[mus]")
        graph.append("[0:a][mus]amix=inputs=2:duration=first:normalize=0[aout]")
        amap = "[aout]"
    else:
        amap = "0:a"

    preset, crf = ("veryfast", "26") if preview else ("medium", "18")
    cmd += ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", amap,
            "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{duration:.3f}",
            "-movflags", "+faststart", str(out)]
    bins.run(cmd)
    return out
