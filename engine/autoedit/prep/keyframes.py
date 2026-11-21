from pathlib import Path

from autoedit import bins


def frame_at(video: Path, t: float, out: Path, width: int = 540) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    bins.run([bins.tool_path("ffmpeg"), "-y", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(video),
              "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", str(out)])
    return out


def downscale_image(src: Path, out: Path, max_side: int = 768) -> Path:
    """JPEG copy of an image (EXIF-rotated, flattened on white) with its long side at most max_side px."""
    from PIL import Image, ImageOps
    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as opened:
        im = ImageOps.exif_transpose(opened)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.getchannel("A"))
            im = bg
        else:
            im = im.convert("RGB")
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        im.save(out, "JPEG", quality=85)
    return out


def extract_keyframes(video: Path, out_dir: Path, duration: float, n: int = 6) -> list[Path]:
    return [frame_at(video, duration * (i + 0.5) / n, out_dir / f"kf_{i}.jpg") for i in range(n)]
