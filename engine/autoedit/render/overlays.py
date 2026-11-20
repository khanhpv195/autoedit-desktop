"""Still overlays rendered with Pillow (CTA as PNG so emoji render, spec 4.5)."""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from autoedit.resources import assets_dir

MAX_W = 960
PAD_X, PAD_Y = 36, 22


def font_path() -> Path:
    return assets_dir() / "fonts" / "BeVietnamPro-ExtraBold.ttf"


def emoji_font() -> tuple[Path, int] | None:
    if sys.platform == "darwin":
        p = Path("/System/Library/Fonts/Apple Color Emoji.ttc")
        return (p, 160) if p.exists() else None
    if os.name == "nt":
        p = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "seguiemj.ttf"
        return (p, 109) if p.exists() else None
    return None


def _is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return cp >= 0x1F000 or 0x2600 <= cp <= 0x27BF or cp in (0xFE0F, 0x200D)


def split_emoji(text: str) -> list[tuple[str, bool]]:
    runs: list[tuple[str, bool]] = []
    for ch in text:
        e = _is_emoji(ch)
        if runs and runs[-1][1] == e:
            runs[-1] = (runs[-1][0] + ch, e)
        else:
            runs.append((ch, e))
    return runs


def _render_line(line: str, font: ImageFont.FreeTypeFont, size: int) -> Image.Image:
    ef = emoji_font()
    tiles: list[Image.Image] = []
    for run, is_e in split_emoji(line):
        if is_e:
            if not ef:
                continue
            efont = ImageFont.truetype(str(ef[0]), ef[1])
            box = efont.getbbox(run)
            tile = Image.new("RGBA", (box[2] - box[0] + 4, box[3] - box[1] + 4), (0, 0, 0, 0))
            ImageDraw.Draw(tile).text((-box[0] + 2, -box[1] + 2), run, font=efont, embedded_color=True)
            h = int(size * 1.05)
            tiles.append(tile.resize((max(1, int(tile.width * h / tile.height)), h), Image.LANCZOS))
        else:
            box = font.getbbox(run)
            tile = Image.new("RGBA", (max(1, box[2]), int(size * 1.25)), (0, 0, 0, 0))
            ImageDraw.Draw(tile).text((0, int(size * 0.1)), run, font=font, fill=(255, 255, 255, 255))
            tiles.append(tile)
    w = sum(t.width for t in tiles) or 1
    h = max((t.height for t in tiles), default=int(size * 1.25))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x = 0
    for t in tiles:
        img.alpha_composite(t, (x, (h - t.height) // 2))
        x += t.width
    return img


def _wrap(text: str, font: ImageFont.FreeTypeFont) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and font.getlength(trial) > MAX_W - 2 * PAD_X:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def text_card(text: str, out: Path, size: int = 84, bg: tuple = (254, 44, 85, 235)) -> Path:
    font = ImageFont.truetype(str(font_path()), size)
    rendered = [_render_line(l, font, size) for l in _wrap(text.upper(), font)]
    w = min(MAX_W, max(r.width for r in rendered) + 2 * PAD_X)
    h = sum(r.height for r in rendered) + 2 * PAD_Y
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((0, 0, w - 1, h - 1), radius=28, fill=bg)
    y = PAD_Y
    for r in rendered:
        card.alpha_composite(r, ((w - r.width) // 2, y))
        y += r.height
    out.parent.mkdir(parents=True, exist_ok=True)
    card.save(out)
    return out


def prepare_logo(src: Path, out: Path, max_w: int = 200) -> Path:
    with Image.open(src) as opened:
        im = opened.convert("RGBA")
    h = max(1, round(im.height * max_w / im.width))
    im.resize((max_w, h), Image.LANCZOS).save(out)
    return out
