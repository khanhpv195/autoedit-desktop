import pytest

from autoedit.edl import TAIL, EdlError, Range, validate_edl
from autoedit.render.captions import Cue, TimedWord, hide_cues, write_ass
from autoedit.render.pipeline import _muted, with_tail
from autoedit.transcript import Word

# clip 1: 0-10 (room noise, no words); clip 2: 10-30 (seller talks 10.5-27.0 on the timeline)
SPANS = [("a", 0.0, 10.0), ("b", 10.0, 30.0)]
WORDS = [Word("Chào", 10.5, 10.9), Word("cả", 10.9, 11.2), Word("nhà", 11.2, 11.6),
         Word("mua", 20.0, 20.4), Word("ngay", 20.4, 20.8), Word("nhé", 26.6, 27.0)]


def v(raw):
    return validate_edl(raw, WORDS, 30.0, spans=SPANS)


def test_audio_track_from_clip_2_under_clip_1_then_clip_2_picture():
    # picture: clip 1 whole (10 s), then clip 2 from its own second 10 (lip sync); sound: clip 2 from 0 to the end
    edl, notes = v({"keep": [{"start": 0, "end": 10}, {"start": 20, "end": 30}],
                    "audio_source": 2, "mute": [1]})
    a = edl.audio
    assert a.source == 2 and a.a_in == 0.0 and a.start == 10.0
    assert a.end >= 27.0                                   # every word up to the last one is heard
    assert edl.output_duration() == pytest.approx(a.duration + TAIL, abs=0.05)
    assert not any("lip sync" in n for n in notes)
    assert [w.text for w in edl.heard_words(WORDS)][-1] == "nhé"
    d = edl.to_dict()
    assert d["audio_source"] == 2 and d["mute"] == [1] and d["audio_in"] == 0.0


def test_audio_out_before_the_last_word_gets_a_note():
    _, notes = v({"keep": [{"start": 0, "end": 10}, {"start": 20, "end": 30}], "audio_source": 2,
                  "audio_out": 12.0})
    assert any("cuts 1 words" in n and "'nhé'" in n for n in notes)


def test_picture_shorter_than_the_audio_is_an_error():
    with pytest.raises(EdlError, match="picture lasts"):
        v({"keep": [{"start": 0, "end": 5}], "audio_source": 2})


def test_off_sync_speaker_picture_gets_a_note():
    _, notes = v({"keep": [{"start": 0, "end": 10}, {"start": 12, "end": 30}], "audio_source": 2})
    assert any("lip sync" in n and "20.00" in n for n in notes)


def test_audio_clip_cannot_be_muted_and_voiceover_excludes_audio():
    with pytest.raises(EdlError, match="cannot also be muted"):
        v({"keep": [{"start": 0, "end": 30}], "audio_source": 2, "mute": [2]})
    with pytest.raises(EdlError, match="voiceover"):
        validate_edl({"keep": [{"start": 0, "end": 30}], "audio_source": 2}, WORDS, 30.0, spans=SPANS,
                     voiceover_on=True)


def test_mute_without_audio_track_hides_that_clips_words():
    edl, _ = v({"keep": [{"start": 10.4, "end": 11.8}, {"start": 19.9, "end": 21.0}], "mute": [2]})
    assert edl.mute == [2] and edl.heard_words(WORDS) == []
    assert _muted(edl.ordered(), edl.muted_spans) == [True, True]


def test_tail_extends_the_last_range_inside_its_clip_only():
    out = with_tail([Range(0.0, 5.0), Range(12.0, 15.0)], SPANS, 30.0)
    assert out[-1].end == pytest.approx(15.0 + TAIL)
    assert with_tail([Range(0.0, 9.9)], SPANS, 30.0)[-1].end == pytest.approx(10.0)    # clip 1 ends at 10
    assert with_tail([Range(5.0, 6.0), Range(1.0, 4.9)], SPANS, 30.0)[-1].end == pytest.approx(5.0)


def test_hide_cues_drops_and_trims_cues_in_windows():
    w = [TimedWord("a", 0, 1, 0, 0)]
    cues = [Cue(0.5, 2.0, w), Cue(3.0, 4.0, w), Cue(8.0, 9.5, w), Cue(9.6, 10.0, w)]
    out = hide_cues(cues, [(0.0, 2.5), (9.0, 11.0)])
    assert [(c.start, c.end) for c in out] == [(3.0, 4.0), (8.0, 9.0)]


def test_fashion_band_is_top_aligned_near_y_620(tmp_path):
    ass = write_ass([Cue(0.2, 1.0, [TimedWord("chào", 0.2, 1.0, 0.2, 0)])], tmp_path / "c.ass", "fashion")
    style = next(l for l in ass.read_text(encoding="utf-8").splitlines() if l.startswith("Style: Caption"))
    f = style.split(",")
    assert f[18] == "8" and f[21] == "620"


def _style(ass):
    return next(l for l in ass.read_text(encoding="utf-8").splitlines() if l.startswith("Style: Caption")).split(",")


def test_caption_band_follows_the_edl_position_over_the_niche():
    from autoedit.render.captions import caption_band
    assert caption_band("thoi-trang") == "fashion" and caption_band("khac") == "bottom"
    assert caption_band("thoi-trang", "bottom") == "low"
    assert caption_band("khac", "middle") == "fashion"
    assert caption_band("khac", "top") == "top"


def test_small_captions_use_a_smaller_font(tmp_path):
    cue = [Cue(0.2, 1.0, [TimedWord("chào", 0.2, 1.0, 0.2, 0)])]
    normal = int(_style(write_ass(cue, tmp_path / "n.ass", "bottom"))[2])
    small = int(_style(write_ass(cue, tmp_path / "s.ass", "bottom", "small"))[2])
    large = int(_style(write_ass(cue, tmp_path / "l.ass", "bottom", "large"))[2])
    assert small < normal < large
    top = _style(write_ass(cue, tmp_path / "t.ass", "top"))
    assert top[18] == "8"
    low = _style(write_ass(cue, tmp_path / "w.ass", "low"))
    assert low[18] == "2" and int(low[21]) < 540
