"""Final pass: base -> b-roll images -> hook -> logo -> CTA -> subtitles LAST (Hard Rule 1); music ducked under speech."""
import re
from pathlib import Path, PurePath

from autoedit import bins
from autoedit.resources import assets_dir

HOOK_SECONDS = 2.5
CTA_SECONDS = 3.5     # from the closing line: 2 s was gone before viewers found the cart


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


FPS = 30
BROLL_ZOOM = 0.06
VIDEO_EXT = {".mov", ".mp4"}
CTA_X, CTA_Y = 48, 1250     # bottom-left, its ↙ pointing at TikTok's product link (y ~1440-1520, x ~24-420);
                             # captions are hidden while it shows
END_FADE = 0.15


def broll_chain(idx: int, src: str, start: float, end: float, w: int, h: int) -> list[str]:
    """Filters turning one still (input `src`) into a w x h clip that zooms 1.0 -> 1.06 and sits on the timeline at
    [start, end): 9:16 cover crop first (oversampled 2x so the zoom stays smooth), then zoompan, then a PTS shift."""
    n = max(2, round((end - start) * FPS))
    return [f"[{src}]scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},setsar=1,"
            f"zoompan=z='1+{BROLL_ZOOM}*on/{n - 1}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={n}:s={w}x{h}:fps={FPS},"
            f"format=yuv420p,setpts=PTS-STARTPTS+{start:.3f}/TB[br{idx}]"]


HOOK_Y = {"top": 300, "middle": 680, "lower": 930}     # card top (1080x1920); captions start ~1200


def compose(base: Path, out: Path, *, duration: float, ass: Path, hook_png: Path | None,
            logo_png: Path | None, cta_png: Path | None, music: Path | None,
            speech: list[tuple[float, float]], duck_db: float, preview: bool,
            broll: list[tuple[Path, float, float]] = (), voice: list[tuple[Path, float]] = (),
            hook_position: str = "middle", audio_end: float | None = None,
            cta_seconds: float = CTA_SECONDS) -> Path:
    """broll: (image file, output start, output end) full-frame overlays, drawn on the base before everything else.
    voice: (voiceover line file, output start) mixed over the base audio; `speech` should then be the voice
    intervals so the music ducks under them. audio_end: output second where all sound stops (a END_FADE fade-out
    before it, silence after: the picture's tail is silent)."""
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

    for path, b_start, b_end in broll:
        cmd.extend(["-i", str(path)])
        if Path(path).suffix.lower() in VIDEO_EXT:      # video cutaway: already cut, graded and sized like the base
            graph.append(f"[{idx}:v]setpts=PTS-STARTPTS+{b_start:.3f}/TB[br{idx}]")
        else:
            graph += broll_chain(idx, f"{idx}:v", b_start, b_end, int(1080 * k), int(1920 * k))
        graph.append(f"[{cur}][br{idx}]overlay=x=0:y=0:enable='between(t,{b_start:.3f},{b_end:.3f})'[v{idx}]")
        cur, idx = f"v{idx}", idx + 1
    if hook_png:
        add_overlay(hook_png, "(W-w)/2", HOOK_Y.get(hook_position, HOOK_Y["middle"]), f"between(t,0,{HOOK_SECONDS})")
    if logo_png:
        add_overlay(logo_png, str(int(48 * k)), 120, None)
    if cta_png:
        add_overlay(cta_png, str(int(CTA_X * k)), CTA_Y, f"gte(t,{max(0.0, duration - cta_seconds):.3f})")
    fonts = filter_path(assets_dir() / "fonts")
    graph.append(f"[{cur}]subtitles=filename={filter_path(ass)}:fontsdir={fonts}"
                 f"{':original_size=1080x1920' if preview else ''}[vout]")

    mix = ["[0:a]"]
    if music:
        cmd.extend(["-stream_loop", "-1", "-i", str(music)])
        graph.append(f"[{idx}:a]aresample=48000,volume='{music_volume_expr(speech, duck_db)}':eval=frame,"
                     f"afade=t=out:st={max(0.0, duration - 1):.3f}:d=1[mus]")
        mix.append("[mus]")
        idx += 1
    for j, (path, start) in enumerate(voice):
        cmd.extend(["-i", str(path)])
        ms = max(0, round(start * 1000))
        graph.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[vo{j}]")
        mix.append(f"[vo{j}]")
        idx += 1
    fade = ""
    if audio_end is not None:
        fade = f",afade=t=out:st={max(0.0, audio_end - END_FADE):.3f}:d={END_FADE}"
    if len(mix) > 1:
        graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0{fade}[aout]")
        amap = "[aout]"
    elif fade:
        graph.append(f"[0:a]anull{fade}[aout]")
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
