import pytest
from autoedit.edl import sentence_edge_notes, Range
from autoedit.transcript import Word

W = [Word("năm", 1.0, 1.3), Word("nay", 1.3, 1.6), Word("2027", 1.6, 2.2), Word("Đây", 2.2, 2.5), Word("là", 2.5, 2.7),
     Word("bản", 2.7, 3.0), Word("mới", 3.0, 3.4), Word("Em", 4.0, 4.2), Word("mời", 4.2, 4.5), Word("và", 4.5, 4.7),
     Word("kèm", 4.7, 4.9), Word("freeship", 4.9, 5.4), Word("ạ", 5.4, 5.6)]


def test_flags_start_mid_sentence_and_points_to_next_sentence():
    notes = sentence_edge_notes([Range(1.55, 3.45)], W)
    assert len(notes) == 1 and "2027" in notes[0] and "2.20" in notes[0]
    assert "starts at 1.00 ('năm')" in notes[0]


def test_flags_end_mid_sentence():
    notes = sentence_edge_notes([Range(3.95, 4.95)], W)
    assert len(notes) == 1 and "freeship" in notes[0] and "5.60" in notes[0]


def test_clean_sentence_range_has_no_note():
    assert sentence_edge_notes([Range(2.15, 3.45), Range(3.95, 5.7)], W) == []


def test_only_the_last_range_end_is_checked():
    assert sentence_edge_notes([Range(3.95, 4.95), Range(2.15, 3.45)], W) == []


def test_last_range_ending_on_a_connective_suggests_trimming_it():
    notes = sentence_edge_notes([Range(3.95, 4.75)], W)       # "Em mời và" | kèm freeship ạ
    assert len(notes) == 1 and "end at 4.50 after 'mời'" in notes[0]


def test_end_just_inside_a_word_drops_that_word():
    from autoedit.edl import validate_edl
    edl, _ = validate_edl({"keep": [{"start": 0.9, "end": 4.55}]}, W, 10.0)      # 4.55: 50 ms into "và", inside the pad after "mời"
    assert edl.keep[0].end <= 4.5 + 1e-6
    edl, _ = validate_edl({"keep": [{"start": 0.9, "end": 4.62}, {"start": 4.9, "end": 5.7}]}, W, 10.0)
    assert edl.keep[0].end >= 4.7 - 1e-6       # well inside "và" (not the video's end): keep it


def test_start_late_inside_a_word_skips_that_word():
    from autoedit.edl import validate_edl
    edl, _ = validate_edl({"keep": [{"start": 2.16, "end": 3.45}]}, W, 10.0)      # 2.15: late in "2027" 1.6-2.2
    assert edl.keep[0].start >= 2.2 - 0.06


def test_video_never_ends_on_a_glued_connective():
    from autoedit.edl import validate_edl
    edl, notes = validate_edl({"keep": [{"start": 0.9, "end": 4.69}]}, W, 10.0)     # ends inside "và" (glued to "kèm")
    assert edl.keep[-1].end == pytest.approx(4.5, abs=0.04)
    assert any("must not end on 'và'" in n for n in notes)


def test_only_the_last_range_is_trimmed():
    from autoedit.edl import validate_edl
    edl, _ = validate_edl({"keep": [{"start": 3.95, "end": 4.69}, {"start": 0.9, "end": 3.45}]}, W, 10.0)
    assert edl.keep[0].end >= 4.7 - 1e-6


def test_short_sentence_tail_is_kept():
    from autoedit.edl import Word, validate_edl
    ws = [Word("Bản", 1.0, 1.3), Word("mới", 1.3, 1.6), Word("vừa", 1.6, 1.9), Word("ra", 1.9, 2.1),
          Word("thôi", 2.1, 2.3), Word("Nhưng", 2.6, 2.9), Word("mà", 2.9, 3.2), Word("đẹp", 3.2, 3.6),
          Word("Mua", 5.0, 5.4), Word("nhé", 5.4, 5.8)]
    edl, notes = validate_edl({"keep": [{"start": 0.95, "end": 2.08}, {"start": 4.95, "end": 5.85}]}, ws, 8.0)
    assert edl.keep[0].end >= 2.3 - 1e-6 and any("'thôi'" in n for n in notes)
    edl, _ = validate_edl({"keep": [{"start": 0.95, "end": 1.58}, {"start": 4.95, "end": 5.85}]}, ws, 8.0)
    assert edl.keep[0].end <= 1.6 + 0.09        # "vừa ra thôi" is too long a tail: left alone


def test_short_sentence_head_is_kept():
    from autoedit.edl import validate_edl
    edl, notes = validate_edl({"keep": [{"start": 2.45, "end": 3.45}, {"start": 0.95, "end": 2.2}]}, W, 10.0)
    assert edl.keep[0].start <= 2.2 and any("'Đây'" in n for n in notes)   # "là bản mới" -> "Đây là bản mới"


def test_stray_first_word_of_next_sentence_is_dropped():
    from autoedit.edl import validate_edl
    edl, notes = validate_edl({"keep": [{"start": 0.95, "end": 4.25}, {"start": 4.85, "end": 5.7}]}, W, 10.0)
    assert edl.keep[0].end <= 3.4 + 0.21 and any("'Em'" in n for n in notes)
