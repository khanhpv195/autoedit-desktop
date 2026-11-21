import pytest

from autoedit.edl import EdlError, validate_edl
from autoedit.render import compose as compose_mod
from autoedit.render.captions import Cue, TimedWord, write_ass
from autoedit.render.compose import compose

# timeline: clip "talk.mp4" 0-20 s (kept), clip "look.mp4" 20-40 s (silent shots for cutaways)
SPANS = [("talk.mp4", 0.0, 20.0), ("look.mp4", 20.0, 40.0)]


def v(extra, keep=None):
    raw = {"keep": keep or [{"start": 0, "end": 10}]} | extra
    return validate_edl(raw, [], 40.0, image_names=[], spans=SPANS)


def test_video_cutaway_roundtrip():
    edl, notes = v({"broll": [{"shot": 25.0, "at": 4.0, "dur": 2.0}]})
    assert edl.to_dict()["broll"] == [{"shot": 25.0, "at": 4.0, "dur": 2.0}]
    assert edl.broll[0].shot == 25.0 and edl.broll[0].image == ""


def test_image_broll_dict_has_no_shot_key():
    edl, _ = validate_edl({"keep": [{"start": 0, "end": 10}], "broll": [{"image": "a.png", "at": 4.0, "dur": 2}]},
                          [], 40.0, image_names=["a.png"])
    assert edl.to_dict()["broll"] == [{"image": "a.png", "at": 4.0, "dur": 2.0}]


def test_cutaway_shot_must_be_inside_the_timeline():
    with pytest.raises(EdlError):
        v({"broll": [{"shot": 45.0, "at": 4.0, "dur": 2.0}]})


def test_cutaway_shot_is_clamped_to_its_clip():
    # 39.0 + 2.0 crosses the end of look.mp4: pulled back so the whole shot is inside the clip
    edl, _ = v({"broll": [{"shot": 39.0, "at": 4.0, "dur": 2.0}]})
    assert 37.9 <= edl.broll[0].shot <= 38.0
    # 19.5 + 2 would run from talk.mp4 into look.mp4: pulled back into talk.mp4
    edl, _ = v({"broll": [{"shot": 19.5, "at": 4.0, "dur": 2.0}]})
    assert 17.9 <= edl.broll[0].shot <= 18.0


def test_cutaway_keeps_hook_and_density_rules():
    edl, notes = v({"broll": [{"shot": 25.0, "at": 0.5, "dur": 2.0}]})
    assert edl.broll[0].at == pytest.approx(2.5)
    edl, notes = v({"broll": [{"shot": 25.0, "at": 3.0, "dur": 2.0}, {"shot": 30.0, "at": 4.0, "dur": 2.0}]})
    assert len(edl.broll) == 1 and any("overlaps" in n for n in notes)


def test_broll_needs_image_or_shot():
    with pytest.raises(EdlError):
        v({"broll": [{"at": 4.0, "dur": 2.0}]})


def test_compose_overlays_video_cutaway_shifted_to_its_window(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(compose_mod.bins, "run", lambda cmd, **k: seen.update(cmd=cmd))
    ass = write_ass([Cue(0.2, 1.0, [TimedWord("a", 0.2, 1.0, 0.2, 0)])], tmp_path / "c.ass")
    compose(tmp_path / "b.mp4", tmp_path / "o.mp4", duration=8.0, ass=ass, hook_png=None, logo_png=None,
            cta_png=None, music=None, speech=[], duck_db=-14, preview=False,
            broll=[(tmp_path / "cut_0.mov", 3.0, 5.0)])
    cmd = seen["cmd"]
    graph = cmd[cmd.index("-filter_complex") + 1].split(";")
    chain = next(g for g in graph if g.startswith("[1:v]"))
    assert "setpts=PTS-STARTPTS+3.000/TB" in chain and "zoompan" not in chain
    assert any("between(t,3.000,5.000)" in g for g in graph)


def test_out_of_range_note_explains_timeline_seconds():
    edl, notes = v({"broll": [{"shot": 25.0, "at": 15.0, "dur": 2.0}]})
    assert edl.broll == [] and any("TIMELINE" in n and "0.00-10.00" in n for n in notes)


def test_cutaway_reusing_footage_is_dropped():
    edl, notes = v({"broll": [{"shot": 25.0, "at": 3.0, "dur": 2.0}, {"shot": 25.5, "at": 7.0, "dur": 2.0}]})
    assert len(edl.broll) == 1 and any("already" in n for n in notes)
    edl, notes = v({"broll": [{"shot": 4.0, "at": 3.0, "dur": 2.0}]})     # shot inside a kept range
    assert edl.broll == [] and any("already" in n for n in notes)


def test_long_single_framing_gets_a_note_when_cutaways_exist():
    _, notes = v({}, keep=[{"start": 0, "end": 16}])
    assert any("one framing" in n and "0.00-16.00" in n for n in notes)
    _, notes = v({"broll": [{"shot": 25.0, "at": 5.0, "dur": 2.5}, {"shot": 30.0, "at": 11.0, "dur": 2.5}]},
                 keep=[{"start": 0, "end": 16}])
    assert not any("one framing" in n for n in notes)


def test_no_framing_note_for_a_single_clip_without_images():
    _, notes = validate_edl({"keep": [{"start": 0, "end": 16}]}, [], 40.0, image_names=[], spans=[("a", 0.0, 40.0)])
    assert not any("one framing" in n for n in notes)
