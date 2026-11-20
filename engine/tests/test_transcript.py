from autoedit.transcript import Word, pack_phrases, format_phrases, speech_duration, words_to_json, words_from_json

W = [Word("Chào", 0.0, 0.3), Word("cả", 0.35, 0.5), Word("nhà", 0.55, 0.8),
     Word("hôm", 2.0, 2.2), Word("nay", 2.25, 2.5)]


def test_pack_splits_on_gap():
    ph = pack_phrases(W, gap=0.5)
    assert [p.text for p in ph] == ["Chào cả nhà", "hôm nay"]
    assert (ph[0].start, ph[0].end) == (0.0, 0.8)


def test_format_phrases():
    assert format_phrases(pack_phrases(W)).splitlines()[1] == "[2.00-2.50] hôm nay"


def test_speech_duration():
    assert abs(speech_duration(W) - (0.8 + 0.5)) < 1e-9


def test_json_roundtrip():
    assert words_from_json(words_to_json(W)) == W


def test_empty():
    assert pack_phrases([]) == [] and speech_duration([]) == 0
