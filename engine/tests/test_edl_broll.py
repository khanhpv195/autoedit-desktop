import pytest

from autoedit.edl import Edl, EdlError, Hook, Range, validate_edl
from autoedit.transcript import Word

IMGS = ["a.png", "b.jpg"]
# silent timeline (no words) so ranges are kept exactly as given
RAW = {"keep": [{"start": 0, "end": 10}]}


def v(extra, keep=None, words=(), dur=30.0, names=IMGS):
    raw = {"keep": keep or RAW["keep"]} | extra
    return validate_edl(raw, list(words), dur, image_names=names)


def test_default_has_no_broll_and_to_dict_lists_it():
    edl, _ = v({})
    assert edl.broll == [] and edl.to_dict()["broll"] == []


def test_valid_broll_roundtrip_and_dur_clamp():
    edl, notes = v({"broll": [{"image": "a.png", "at": 4.0, "dur": 9}]})
    assert edl.to_dict()["broll"] == [{"image": "a.png", "at": 4.0, "dur": 4.0}]
    edl, _ = v({"broll": [{"image": "a.png", "at": 4.0, "dur": 0.2}]})
    assert edl.broll[0].dur == 1.5


def test_unknown_image_is_an_error():
    with pytest.raises(EdlError, match="nope.png"):
        v({"broll": [{"image": "nope.png", "at": 4.0, "dur": 2}]})
    with pytest.raises(EdlError):
        v({"broll": [{"image": "a.png", "at": 4.0, "dur": 2}]}, names=())


def test_at_outside_kept_range_dropped_with_note():
    edl, notes = v({"broll": [{"image": "a.png", "at": 15.0, "dur": 2}]})
    assert edl.broll == [] and any("kept range" in n for n in notes)


def test_dur_cut_to_range_end_or_dropped():
    edl, _ = v({"broll": [{"image": "a.png", "at": 8.0, "dur": 4}]})
    assert edl.broll[0].dur == pytest.approx(2.0)
    edl, notes = v({"broll": [{"image": "a.png", "at": 9.5, "dur": 3}]})
    assert edl.broll == [] and notes


def test_not_over_hook_seconds():
    # output 0-2.5 is the hook; b-roll at output 1.0 is pushed to 2.5
    edl, _ = v({"hook": {"move_to_front": [0, 6], "text": "HI"}, "broll": [{"image": "a.png", "at": 1.0, "dur": 2}]})
    assert edl.broll[0].at == pytest.approx(2.5)


def test_overlap_and_density_rules():
    edl, notes = v({"broll": [{"image": "a.png", "at": 2.0, "dur": 3}, {"image": "b.jpg", "at": 3.0, "dur": 3}]})
    assert len(edl.broll) == 1 and any("overlaps" in n for n in notes)
    # 10 s of output allows 3 b-rolls
    four = [{"image": "a.png", "at": t, "dur": 1.5} for t in (2.5, 4.5, 6.5, 8.0)]
    edl, notes = v({"broll": four})
    assert len(edl.broll) == 3 and any("per 3s" in n for n in notes)


def test_output_time_mapping_with_hook_reorder():
    edl = Edl(keep=[Range(0, 4), Range(10, 14)], hook=Hook(11, 12.5, "x"))
    # ordered: hook 11-12.5 (out 0-1.5), 0-4 (1.5-5.5), 10-11 (5.5-6.5), 12.5-14 (6.5-8.0)
    assert [(r.start, r.end) for r in edl.ordered()] == [(11, 12.5), (0, 4), (10, 11), (12.5, 14)]
    assert edl.output_time(11.5) == pytest.approx(0.5)
    assert edl.output_time(1.0) == pytest.approx(2.5)
    assert edl.output_time(10.5) == pytest.approx(6.0)
    assert edl.output_time(13.0) == pytest.approx(7.0)
    assert edl.output_time(6.0) is None
    assert edl.output_span(3.0, 2.0) == pytest.approx((4.5, 5.5))    # cut at the end of its range


def test_snapped_range_used_for_membership():
    words = [Word("a", 1.0, 1.4), Word("b", 5.0, 5.5)]
    edl, _ = v({"keep": [{"start": 1.2, "end": 5.2}], "broll": [{"image": "a.png", "at": 3.0, "dur": 2}]}, words=words)
    assert len(edl.broll) == 1
