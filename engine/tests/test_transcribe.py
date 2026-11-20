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
