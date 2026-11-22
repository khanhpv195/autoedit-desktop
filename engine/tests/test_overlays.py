from PIL import Image
from autoedit.render import overlays as ov


def _info(path):
    with Image.open(path) as im:
        return im.size, im.mode


def test_split_emoji():
    assert ov.split_emoji("BẤM GIỎ HÀNG 👇") == [("BẤM GIỎ HÀNG ", False), ("👇", True)]


def test_text_card_size_and_wrap(tmp_path):
    p = ov.text_card("chân ngắn? xem ngay", tmp_path / "h.png")
    (w, h), mode = _info(p)
    assert mode == "RGBA" and 200 < w <= 960
    long = ov.text_card("một câu rất dài để kiểm tra xuống dòng tự động trong thẻ", tmp_path / "l.png")
    assert _info(long)[0][1] > h


def test_text_card_with_emoji_or_fallback(tmp_path, monkeypatch):
    ov.text_card("BẤM GIỎ HÀNG 👇", tmp_path / "c.png")
    monkeypatch.setattr(ov, "emoji_font", lambda: None)
    assert _info(ov.text_card("MUA NGAY 👇", tmp_path / "c2.png"))[0][0] > 100


def test_prepare_logo(tmp_path):
    src = tmp_path / "logo.jpg"; Image.new("RGB", (800, 400), "red").save(src)
    p = ov.prepare_logo(src, tmp_path / "logo.png")
    assert _info(p) == ((200, 100), "RGBA")


def test_cta_card_fits_the_bottom_left_corner_and_draws_its_own_arrow(tmp_path):
    from PIL import Image
    p = ov.cta_card("BẤM GIỎ HÀNG 👇", tmp_path / "cta.png")
    with Image.open(p) as im:
        assert im.width <= ov.CTA_MAX_W and 90 <= im.height <= 160
        right = im.crop((im.width - 110, 20, im.width - 20, im.height - 20)).convert("L")
        assert right.getextrema()[1] > 200       # the white ↙ sits at the right end of the card
