import pytest

from autoedit.duration import parse_duration


@pytest.mark.parametrize("text, want", [
    ("cắt còn 30s", (27.0, 33.0)),
    ("làm video 30 giây", (27.0, 33.0)),
    ("Làm 60s", (54.0, 66.0)),
    ("khoảng 1 phút", (51.0, 69.0)),
    ("video tầm 45s thôi", (38.2, 51.7)),
    ("cắt còn 1p30", (81.0, 99.0)),
    ("dài 1 phút 30 giây", (81.0, 99.0)),
    ("làm 1 phút rưỡi", (81.0, 99.0)),
    ("rút còn nửa phút", (27.0, 33.0)),
    ("dưới 40 giây", (24.0, 40.0)),
    ("tối đa 1 phút", (36.0, 60.0)),
    ("ít nhất 20s", (20.0, 28.0)),
    ("video 30-45s", (30.0, 45.0)),
    ("thời lượng 1-2 phút", (60.0, 120.0)),
    ("30s", (27.0, 33.0)),
    ("45-60 giây", (45.0, 60.0)),
    ("~40s", (34.0, 46.0)),
    ("about 30 seconds, punchy", (25.5, 34.5)),
    ("mở bằng câu chốt giá, cắt còn khoảng 30s nhé", (25.5, 34.5)),
])
def test_lengths(text, want):
    assert parse_duration(text) == want


@pytest.mark.parametrize("text", [
    None, "", "làm ngắn gọn, mở đầu bằng câu chốt giá",
    "hình clip 1 từ 0 đến 44.2s, rồi hình clip 2 từ 44.2s",      # timestamps, not a target
    "giá 159k, 100 xong, free ship",
    "dùng 2 clip, hook 3 chữ",
    "hook trong 3s đầu", "cắt 10s cuối", "giữ lại 5 giây đầu",
])
def test_no_length(text):
    assert parse_duration(text) is None


def test_first_length_wins_over_timestamps():
    assert parse_duration("hình clip 1 từ 0 đến 44.2s, video dài khoảng 1 phút") == (51.0, 69.0)
