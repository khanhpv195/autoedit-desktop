import json
from pathlib import Path
import pytest
import importlib
from autoedit.transcript import Word

# prep/__init__ re-exports the function `transcribe`, shadowing the submodule attribute
tr = importlib.import_module("autoedit.prep.transcribe")
FIX = Path(__file__).parent / "fixtures" / "whisper_sample.json"


def test_parse_fixture_has_words_in_order():
    words = tr.parse_whisper_json(json.loads(FIX.read_text(encoding="utf-8")))
    assert len(words) >= 5
    assert all(w.text.strip() == w.text and w.text for w in words)
    assert all(a.start <= b.start for a, b in zip(words, words[1:]))


def test_parse_applies_lag_and_skips_blank():
    data = {"transcription": [
        {"offsets": {"from": 1000, "to": 1400}, "text": " Chào"},
        {"offsets": {"from": 1400, "to": 1400}, "text": " "},
        {"offsets": {"from": 1500, "to": 1800}, "text": " cả"},
    ]}
    assert tr.parse_whisper_json(data, lag=0.1) == [Word("Chào", 1.1, 1.5), Word("cả", 1.6, 1.9)]


def test_drop_hallucinations():
    real = [Word("a", 0, 0.3), Word("b", 0.4, 0.7)]
    fake = [Word("Cảm", 5.0, 5.01), Word("ơn", 5.01, 5.02), Word("các", 5.02, 5.03), Word("bạn", 5.03, 5.04)]
    single_flat = [Word("ờ", 1.0, 1.02)]
    assert tr.drop_hallucinations(real + single_flat + fake) == real + single_flat


def test_transcribe_uses_cache(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"; video.write_bytes(b"abc")
    calls = []
    monkeypatch.setattr(tr, "_run_whisper", lambda v, wd, lang: calls.append(1) or [Word("x", 0, 1)])
    assert tr.transcribe(video, tmp_path) == [Word("x", 0, 1)]
    assert tr.transcribe(video, tmp_path) == [Word("x", 0, 1)]
    assert len(calls) == 1
    video.write_bytes(b"changed")
    tr.transcribe(video, tmp_path)
    assert len(calls) == 2


@pytest.mark.slow
def test_real_whisper(clip, tmp_path):
    words = tr.transcribe(clip, tmp_path)  # sine tone: expect few/no words, but no crash
    assert isinstance(words, list)


def _line(text, t0, step=0.3):
    return [Word(w, round(t0 + i * step, 2), round(t0 + i * step + 0.25, 2)) for i, w in enumerate(text.split())]


REAL = _line("chị em ơi son này giá 189K thôi nha", 1.0)


@pytest.mark.parametrize("closing", [
    "Cảm ơn các bạn đã theo dõi",
    "cảm ơn các bạn đã xem video",
    "Hãy đăng ký kênh để không bỏ lỡ những video hấp dẫn",
    "Hãy subscribe cho kênh Ghiền Mì Gõ",
    "Subscribe nhé",
    "Đăng ký kênh nha",
])
def test_closing_lines_at_end_are_dropped(closing):
    words = REAL + _line(closing, 6.0)
    assert tr.drop_closing_lines(words) == REAL


@pytest.mark.parametrize("spoken", [
    "cảm ơn mọi người đã xem nhé bấm giỏ hàng để mua liền",
    "theo dõi kênh của shop để nhận mã giảm giá",
    "nhớ like và share cho shop",
    "mua ngay nhé các bạn theo dõi kênh của shop để nhận mã giảm giá nha",
])
def test_seller_speech_with_cta_keeps_every_word(spoken):
    words = _line(spoken, 1.0)
    assert tr.drop_closing_lines(words) == words
    words = REAL + _line(spoken, 6.0)
    assert tr.drop_closing_lines(words) == words


def test_closing_glued_to_a_real_sentence_is_kept():
    words = _line("bấm giỏ hàng nha cảm ơn các bạn đã theo dõi", 1.0)
    assert tr.drop_closing_lines(words) == words


def test_nothing_after_a_non_matching_phrase_is_deleted():
    words = REAL + _line("cảm ơn các bạn đã theo dõi", 6.0) + _line("bấm giỏ hàng nha", 8.0)
    assert tr.drop_closing_lines(words) == words


def test_pure_closing_phrase_in_the_middle_is_kept():
    words = REAL + _line("Cảm ơn các bạn đã theo dõi", 6.0) + _line("giá chỉ 189K thôi", 8.0)
    assert tr.drop_closing_lines(words) == words


def test_isolated_closing_line_in_a_silent_region_is_dropped():
    tail = _line("tạm biệt nhé", 30.0)
    words = REAL + _line("Hãy đăng ký kênh", 10.0) + tail     # 2+ s of silence on both sides
    out = tr.drop_closing_lines(words)
    assert out == REAL + tail


def test_real_speech_mentioning_follow_in_the_middle_is_kept():
    words = _line("nhớ theo dõi shop để nhận ưu đãi nha", 1.0) + _line("giá chỉ 189K thôi", 4.0)
    assert tr.drop_closing_lines(words) == words
    assert tr.drop_closing_lines(REAL) == REAL and tr.drop_closing_lines([]) == []
