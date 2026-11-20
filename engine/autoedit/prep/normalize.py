import os
from pathlib import Path

from autoedit import bins
from autoedit.fsutil import part_path
from autoedit.prep.probe import MediaInfo

W, H, FPS = 1080, 1920, 30
TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
           "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def build_filter(info: MediaInfo) -> str:
    pre = f"{TONEMAP}," if info.hdr else ""
    if info.portrait:
        # ffmpeg auto-rotates on decode. Cover the frame (upscaling allowed), centre-crop: no black bars.
        return (f"[0:v]{pre}scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={W}:{H},setsar=1,fps={FPS},format=yuv420p[v]")
    # Landscape: sharp copy fitted to width, centred over a blurred, cropped fill.
    return (f"[0:v]{pre}split=2[bg][fg];"
            f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=20:2[bgb];"
            f"[fg]scale=w='min({W},iw)':h=-2[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={FPS},format=yuv420p[v]")


def normalize(src: Path, dst: Path, info: MediaInfo) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = part_path(dst)
    cmd = [bins.tool_path("ffmpeg"), "-y", "-v", "error", "-i", str(src)]
    if not info.has_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += ["-filter_complex", build_filter(info), "-map", "[v]",
            "-map", "1:a" if not info.has_audio else "0:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "16",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-t", f"{info.duration:.3f}", "-movflags", "+faststart", str(tmp)]
    try:
        bins.run(cmd)
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)
    return dst
