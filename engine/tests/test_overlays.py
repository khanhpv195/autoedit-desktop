from PIL import Image
from autoedit.render import overlays as ov


def test_split_emoji():
    assert ov.split_emoji("BẤM GIỎ HÀNG 👇") == [("BẤM GIỎ HÀNG ", False), ("👇", True)]


def test_text_card_size_and_wrap(tmp_path):
    p = ov.text_card("chân ngắn? xem ngay", tmp_path / "h.png")
    im = Image.open(p)
    assert im.mode == "RGBA" and 200 < im.width <= 960
    long = ov.text_card("một câu rất dài để kiểm tra xuống dòng tự động trong thẻ", tmp_path / "l.png")
    assert Image.open(long).height > im.height


def test_text_card_with_emoji_or_fallback(tmp_path, monkeypatch):
    ov.text_card("BẤM GIỎ HÀNG 👇", tmp_path / "c.png")
    monkeypatch.setattr(ov, "emoji_font", lambda: None)
    assert Image.open(ov.text_card("MUA NGAY 👇", tmp_path / "c2.png")).width > 100


def test_prepare_logo(tmp_path):
    src = tmp_path / "logo.jpg"; Image.new("RGB", (800, 400), "red").save(src)
    p = ov.prepare_logo(src, tmp_path / "logo.png")
    assert Image.open(p).size == (200, 100) and Image.open(p).mode == "RGBA"
