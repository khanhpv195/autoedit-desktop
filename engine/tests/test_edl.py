import pytest
from autoedit.edl import validate_edl, EdlError, DEFAULT_CTA
from autoedit.transcript import Word

# Two phrases: 1.0-2.0 and 4.0-6.0 ; clip 8s
WORDS = [Word("một", 1.0, 1.4), Word("hai", 1.5, 2.0),
         Word("ba", 4.0, 4.5), Word("bốn", 4.6, 5.2), Word("năm", 5.3, 6.0)]


def v(raw, words=WORDS, dur=8.0):
    return validate_edl(raw, words, dur)


FRAME = 1 / 30


def on_grid(t):
    return abs(t * 30 - round(t * 30)) < 1e-6


def test_snaps_inside_word_and_pads():
    edl, notes = v({"keep": [{"start": 1.2, "end": 1.7}]})  # starts inside "một", ends inside "hai"
    r = edl.keep[0]
    assert r.start == pytest.approx(1.0 - 0.05, abs=FRAME / 2 + 1e-6) and r.end == pytest.approx(2.0 + 0.08, abs=FRAME / 2 + 1e-6)
    assert on_grid(r.start) and on_grid(r.end)


def test_silent_footage_inside_range_is_kept():
    """I4: keep [3.0, 6.5] over speech at 4.0-6.0 must not be trimmed to the speech."""
    edl, _ = v({"keep": [{"start": 3.0, "end": 6.5}]})
    r = edl.keep[0]
    assert r.start == pytest.approx(3.0, abs=FRAME / 2 + 1e-6) and r.end == pytest.approx(6.5, abs=FRAME / 2 + 1e-6)


def test_edge_inside_word_snaps_but_silent_edge_stays():
    edl, _ = v({"keep": [{"start": 0.2, "end": 5.0}]})  # silent start, ends inside "bốn" (4.6-5.2)
    r = edl.keep[0]
    assert r.start == pytest.approx(0.2, abs=FRAME / 2 + 1e-6)
    assert r.end == pytest.approx(5.25, abs=FRAME)   # pad clamped to mid-gap before 'năm'


def test_keep_order_is_play_order():
    """B2: ranges play in the given order, no sorting."""
    edl, _ = v({"keep": [{"start": 4.0, "end": 6.0}, {"start": 1.0, "end": 2.0}]})
    got = [x for r in edl.keep for x in (r.start, r.end)]
    assert got == pytest.approx([3.95, 6.08, 0.95, 2.08], abs=FRAME / 2 + 1e-6)
    assert [r.start for r in edl.ordered()] == [r.start for r in edl.keep]
    assert edl.output_time(1.0) == pytest.approx(6.08 - 3.95 + 0.05, abs=FRAME)


def test_overlapping_ranges_are_rejected():
    with pytest.raises(EdlError, match=r"keep\[2\].*chồng lên keep\[0\].*một lần"):
        v({"keep": [{"start": 1.0, "end": 2.0}, {"start": 4.0, "end": 6.0}, {"start": 1.5, "end": 2.0}]})
    with pytest.raises(EdlError, match="chồng"):
        validate_edl({"keep": [{"start": 0.0, "end": 3.0}, {"start": 5.0, "end": 6.0}, {"start": 2.0, "end": 4.0}]},
                     [], 8.0)


def test_overlap_error_quotes_raw_numbers():
    """The agent sees its own numbers, not the snapped/padded ones."""
    with pytest.raises(EdlError, match=r"keep\[2\] \(1\.5–2\.5\) chồng lên keep\[0\] \(1\.2–1\.7\)"):
        v({"keep": [{"start": 1.2, "end": 1.7}, {"start": 4.0, "end": 6.0}, {"start": 1.5, "end": 2.5}]})


MID = [Word("một", 1.0, 1.4), Word("áo", 5.3, 5.7), Word("len", 8.0, 8.5)]


def test_mid_word_split_of_one_take_merges():
    """Splitting a take mid-word (word at 5.3-5.7, split at 5.5) is one continuous take, not an overlap."""
    edl, _ = validate_edl({"keep": [{"start": 0.0, "end": 5.5}, {"start": 5.5, "end": 10.0}]}, MID, 12.0)
    assert [(r.start, r.end) for r in edl.keep] == [(0.0, pytest.approx(10.0))]


def test_reversed_mid_word_split_is_clamped_not_rejected():
    """Reversed order of the same split: padding makes the snapped ranges overlap; the later source range is
    clamped to start where the earlier ends, and the play order is kept."""
    edl, _ = validate_edl({"keep": [{"start": 5.5, "end": 10.0}, {"start": 0.0, "end": 5.5}]}, MID, 12.0)
    a, b = edl.keep
    assert a.start > b.start            # play order preserved: the later footage plays first
    assert a.start == pytest.approx(b.end) and a.end == pytest.approx(10.0)
    assert b.end >= 5.7                 # the split word is kept whole, once


def test_list_adjacent_touching_ranges_merge():
    edl, _ = validate_edl({"keep": [{"start": 0.0, "end": 2.0}, {"start": 2.02, "end": 3.0},
                                    {"start": 5.0, "end": 6.0}]}, [], 8.0)
    assert [(r.start, r.end) for r in edl.keep] == [(0.0, 3.0), (5.0, 6.0)]


def test_touching_but_not_list_adjacent_stay_separate():
    edl, _ = validate_edl({"keep": [{"start": 2.0, "end": 3.0}, {"start": 5.0, "end": 6.0},
                                    {"start": 0.0, "end": 2.0}]}, [], 8.0)
    assert [(r.start, r.end) for r in edl.keep] == [(2.0, 3.0), (5.0, 6.0), (0.0, 2.0)]


def test_coverage_rule_skipped_with_voiceover():
    with pytest.raises(EdlError, match="30%"):
        v({"keep": [{"start": 1.0, "end": 1.4}]})
    edl, _ = validate_edl({"keep": [{"start": 1.0, "end": 1.4}, {"start": 6.5, "end": 7.5}]}, WORDS, 8.0,
                          voiceover_on=True)
    assert len(edl.keep) == 2


def test_hook_text_without_move_to_front():
    edl, _ = v({"keep": [{"start": 4.0, "end": 6.0}, {"start": 1.0, "end": 2.0}], "hook": {"text": "XEM NGAY"}})
    assert edl.hook.text == "XEM NGAY" and edl.hook.start is None
    assert [r.start for r in edl.ordered()] == [r.start for r in edl.keep]   # nothing moved
    assert edl.to_dict()["hook"] == {"text": "XEM NGAY", "position": "middle"}
    again, _ = v(edl.to_dict())
    assert again.to_dict() == edl.to_dict()
    with pytest.raises(EdlError, match="5"):
        v({"keep": [{"start": 1.0, "end": 6.0}], "hook": {"text": "một hai ba bốn năm sáu"}})


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
    assert edl.hook.text == "XEM NGAY" and edl.hook.start == pytest.approx(3.95, abs=FRAME / 2 + 1e-6)
    with pytest.raises(EdlError, match="5"):
        v({"keep": [{"start": 1.0, "end": 6.0}], "hook": {"move_to_front": [4.0, 5.2], "text": "một hai ba bốn năm sáu"}})


def test_ordered_puts_hook_first_and_removes_overlap():
    edl, _ = v({"keep": [{"start": 1.0, "end": 2.0}, {"start": 4.0, "end": 6.0}],
                "hook": {"move_to_front": [4.6, 5.2], "text": "HOOK"}})
    o = edl.ordered()
    assert o[0].start == pytest.approx(4.55, abs=FRAME) and o[0].end == pytest.approx(5.25, abs=FRAME)
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


TIGHT = [Word("a", 1.0, 1.5), Word("b", 1.52, 2.0), Word("c", 2.03, 2.5), Word("d", 3.0, 3.5)]


def inside_word(t, words):
    return any(w.start + 1e-6 < t < w.end - 1e-6 for w in words)


def test_padding_never_crosses_into_neighbour_words():
    """I3: tight gaps, hook on word b only."""
    edl, _ = v({"keep": [{"start": 1.0, "end": 3.5}], "hook": {"move_to_front": [1.52, 2.0], "text": "HOOK"}},
               TIGHT, 4.0)
    h = edl.ordered()[0]
    assert h.start >= 1.5 - 1e-6 and h.end <= 2.03 + 1e-6      # not into a (ends 1.5) nor c (starts 2.03)
    for r in edl.ordered():
        assert not inside_word(r.start, TIGHT) and not inside_word(r.end, TIGHT), (r.start, r.end)


def test_hook_split_never_starts_mid_word():
    edl, _ = v({"keep": [{"start": 1.0, "end": 3.5}], "hook": {"move_to_front": [1.52, 2.0], "text": "HOOK"}},
               TIGHT, 4.0)
    for r in edl.ordered()[1:]:
        assert not inside_word(r.start, TIGHT) and not inside_word(r.end, TIGHT)
    assert edl.ordered()[1].start == pytest.approx(edl.hook.end) or edl.ordered()[1].end <= edl.hook.start + 1e-9


def test_keep_padding_clamped_to_gap_midpoint():
    edl, _ = v({"keep": [{"start": 1.52, "end": 2.0}, {"start": 3.0, "end": 3.5}]}, TIGHT, 4.0)
    r = edl.keep[0]
    assert r.start >= 1.5 - 1e-6 and r.end <= 2.03 + 1e-6 and r.duration >= 0.4


def test_all_edges_on_frame_grid_when_there_is_room():
    edl, _ = v({"keep": [{"start": 1.2, "end": 1.7}, {"start": 3.0123, "end": 3.9}]})
    assert all(on_grid(r.start) and on_grid(r.end) for r in edl.keep)


@pytest.mark.parametrize("bad", [
    {"keep": [{"start": 1.0, "end": 6.0}], "caption_fixes": [{"at": 4.0, "wrong": "ba", "right": ""}]},
    {"keep": [{"start": 1.0, "end": 6.0}], "caption_fixes": [{"at": 4.0, "wrong": " ", "right": "BA"}]},
    {"keep": [{"start": 1.0, "end": 6.0}], "emphasis": [{"at": 4.0, "word": ""}]},
])
def test_rejects_empty_fix_text(bad):
    with pytest.raises(EdlError):
        v(bad)


def test_rejects_empty_hook_text():
    with pytest.raises(EdlError, match="empty"):
        v({"keep": [{"start": 1.0, "end": 6.0}], "hook": {"move_to_front": [4.0, 5.2], "text": "  "}})


def test_hook_position_is_kept_and_checked():
    edl, _ = v({"keep": [{"start": 1.0, "end": 6.0}], "hook": {"text": "XEM NGAY", "position": "lower"}})
    assert edl.hook.position == "lower" and edl.to_dict()["hook"]["position"] == "lower"
    with pytest.raises(EdlError):
        v({"keep": [{"start": 1.0, "end": 6.0}], "hook": {"text": "XEM NGAY", "position": "left"}})
