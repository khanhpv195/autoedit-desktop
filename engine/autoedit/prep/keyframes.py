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


SHEET_COLS, SHEET_ROWS, SHEET_TILE = 3, 3, 300


def _wrap(text: str, width: int) -> list[str]:
    return [text[i:i + width] for i in range(0, len(text), width)][:3] or [""]


def contact_sheets(items: list[tuple[str, Path]], out_dir: Path, cols: int = SHEET_COLS, rows: int = SHEET_ROWS,
                   tile: int = SHEET_TILE) -> list[tuple[list[str], Path]]:
    """Grid JPEGs (cols x rows tiles each) of the given (name, image) pairs, every tile labelled with its name drawn
    on a bar under the picture. Returns [(names on the sheet in reading order, sheet path)]."""
    from PIL import Image, ImageDraw, ImageFont
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("sheet_*.jpg"):
        old.unlink(missing_ok=True)
    try:
        font = ImageFont.load_default(size=15)
    except TypeError:      # Pillow < 10.1 has a fixed-size default font
        font = ImageFont.load_default()
    bar, per, sheets = 3 * 17 + 6, cols * rows, []
    for s in range(0, len(items), per):
        chunk = items[s:s + per]
        n_rows = -(-len(chunk) // cols)
        sheet = Image.new("RGB", (cols * tile, n_rows * (tile + bar)), (255, 255, 255))
        draw = ImageDraw.Draw(sheet)
        for k, (name, path) in enumerate(chunk):
            x, y = (k % cols) * tile, (k // cols) * (tile + bar)
            with Image.open(path) as im:
                im = im.convert("RGB")
                im.thumbnail((tile - 4, tile - 4), Image.LANCZOS)
                sheet.paste(im, (x + (tile - im.width) // 2, y + (tile - im.height) // 2))
            draw.rectangle([x, y + tile, x + tile - 1, y + tile + bar - 1], fill=(0, 0, 0))
            for li, line in enumerate(_wrap(name, 30)):
                draw.text((x + 4, y + tile + 3 + li * 17), line, fill=(255, 255, 255), font=font)
            draw.rectangle([x, y, x + tile - 1, y + tile + bar - 1], outline=(128, 128, 128))
        path = out_dir / f"sheet_{len(sheets)}.jpg"
        sheet.save(path, "JPEG", quality=85)
        sheets.append(([n for n, _ in chunk], path))
    return sheets
