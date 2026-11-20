import pytest
from autoedit.edl import validate_edl, EdlError, DEFAULT_CTA
from autoedit.transcript import Word

# Two phrases: 1.0-2.0 and 4.0-6.0 ; clip 8s
WORDS = [Word("một", 1.0, 1.4), Word("hai", 1.5, 2.0),
         Word("ba", 4.0, 4.5), Word("bốn", 4.6, 5.2), Word("năm", 5.3, 6.0)]


def v(raw, words=WORDS, dur=8.0):
    return validate_edl(raw, words, dur)


def test_snaps_inside_word_and_pads():
    edl, notes = v({"keep": [{"start": 1.2, "end": 1.7}]})  # starts inside "một", ends inside "hai"
    r = edl.keep[0]
    assert r.start == pytest.approx(1.0 - 0.05) and r.end == pytest.approx(2.0 + 0.08)


def test_snaps_from_silence_to_next_word():
    edl, _ = v({"keep": [{"start": 3.0, "end": 6.5}]})
    assert edl.keep[0].start == pytest.approx(3.95) and edl.keep[0].end == pytest.approx(6.08)


def test_merges_overlaps_and_sorts():
    edl, _ = v({"keep": [{"start": 4.0, "end": 6.0}, {"start": 1.0, "end": 2.0}, {"start": 1.5, "end": 2.0}]})
    assert [(round(r.start, 2), round(r.end, 2)) for r in edl.keep] == [(0.95, 2.08), (3.95, 6.08)]


def test_drops_short_segment_with_note():
    words = WORDS + [Word("ừ", 7.0, 7.1)]
    edl, notes = v({"keep": [{"start": 1.0, "end": 2.0}, {"start": 4.0, "end": 6.0}, {"start": 7.0, "end": 7.1}]}, words)
    assert len(edl.keep) == 2 and any("0.4" in n for n in notes)


def test_rejects_too_little_speech():
    with pytest.raises(EdlError, match="30%"):
        v({"keep": [{"start": 1.0, "end": 1.4}]})


def test_rejects_out_of_bounds_and_inverted():
    with pytest.raises(EdlError):
        v({"keep": [{"start": 5.0, "end": 4.0}]})
    with pytest.raises(EdlError):
        v({"keep": [{"start": 1.0, "end": 99.0}]})
    with pytest.raises(EdlError):
        v({"keep": []})


def test_hook_rules():
    edl, _ = v({"keep": [{"start": 1.0, "end": 6.0}], "hook": {"move_to_front": [4.0, 5.2], "text": "XEM NGAY"}})
    assert edl.hook.text == "XEM NGAY" and edl.hook.start == pytest.approx(3.95)
    with pytest.raises(EdlError, match="5"):
        v({"keep": [{"start": 1.0, "end": 6.0}], "hook": {"move_to_front": [4.0, 5.2], "text": "một hai ba bốn năm sáu"}})


def test_ordered_puts_hook_first_and_removes_overlap():
    edl, _ = v({"keep": [{"start": 1.0, "end": 2.0}, {"start": 4.0, "end": 6.0}],
                "hook": {"move_to_front": [4.6, 5.2], "text": "HOOK"}})
    o = edl.ordered()
    assert o[0].start == pytest.approx(4.55) and o[0].end == pytest.approx(5.28)
    # the 4.0-6.0 keep is split around the hook; pieces < 0.4s dropped
    assert all(not (r.start < o[0].end and r.end > o[0].start) for r in o[1:])
    assert edl.output_duration() == pytest.approx(sum(r.duration for r in o))


def test_defaults():
    edl, _ = v({"keep": [{"start": 1.0, "end": 6.0}]})
    assert edl.cta_text == DEFAULT_CTA and edl.hook is None and edl.music_use is True and edl.music_duck_db == -14


def test_no_speech_clip_keeps_edges():
    edl, _ = validate_edl({"keep": [{"start": 0.5, "end": 3.0}]}, [], 4.0)
    assert (edl.keep[0].start, edl.keep[0].end) == (0.5, 3.0)


def test_to_dict_roundtrip():
    edl, _ = v({"keep": [{"start": 1.0, "end": 6.0}], "caption_fixes": [{"at": 4.0, "wrong": "ba", "right": "BA"}],
                "emphasis": [{"at": 4.6, "word": "bốn"}], "cta_text": "MUA NGAY"})
    again, _ = v(edl.to_dict())
    assert again.to_dict() == edl.to_dict()
