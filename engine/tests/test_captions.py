from autoedit.edl import Range, CaptionFix, Emphasis
from autoedit.render.captions import map_words, chunk, build_cues, write_ass, speech_intervals
from autoedit.transcript import Word

WORDS = [Word("chào", 1.0, 1.2), Word("cả", 1.25, 1.4), Word("nhà", 1.45, 1.7),
         Word("son", 5.0, 5.2), Word("này", 5.25, 5.5), Word("giá", 5.6, 5.8), Word("189K", 5.85, 6.3)]


def test_output_timeline_offsets_with_reorder():
    ranges = [Range(4.9, 6.4), Range(0.9, 1.8)]  # hook first, then intro
    tw = map_words(ranges, WORDS, [], [])
    son = next(w for w in tw if w.text == "son")
    chao = next(w for w in tw if w.text == "chào")
    assert abs(son.start - (5.0 - 4.9)) < 1e-6
    assert abs(chao.start - (1.0 - 0.9 + 1.5)) < 1e-6
    assert son.group != chao.group


def test_fix_and_emphasis():
    tw = map_words([Range(0.9, 6.4)], WORDS, [CaptionFix(5.0, "son", "SON KEM")], [Emphasis(5.85, "189k")])
    texts = [w.text for w in tw]
    assert "SON KEM" in texts and "son" not in texts
    assert next(w for w in tw if w.text == "189K").emph


def test_chunk_respects_hard_limit():
    many = [Word(f"w{i}", i * 0.2, i * 0.2 + 0.15) for i in range(14)]
    for c in chunk(map_words([Range(0, 3)], many, [], [])):
        assert 1 <= len(c) <= 6


def test_cues_dont_overlap_and_last_holds():
    cues = build_cues([Range(0.9, 6.4)], WORDS, [], [], total=5.5)
    assert all(a.end <= b.start + 1e-9 for a, b in zip(cues, cues[1:]))
    assert abs(cues[-1].end - 5.45) < 1e-6


def test_speech_intervals_merge():
    iv = speech_intervals([Range(0.9, 6.4)], WORDS)
    assert len(iv) == 2 and iv[0][0] < 0.2


def test_write_ass(tmp_path):
    cues = build_cues([Range(0.9, 6.4)], WORDS, [], [Emphasis(5.85, "189K")], total=5.5)
    text = write_ass(cues, tmp_path / "c.ass").read_text(encoding="utf-8")
    assert "Style: Caption,Be Vietnam Pro ExtraBold,78" in text
    assert text.count("Dialogue:") == len(cues)
    assert "CHÀO CẢ NHÀ" in text and "{\\c&H0000D7FF&}189K" in text


PHRASE = [Word("chị", 18.2, 18.4), Word("em", 18.45, 18.6), Word("ơi", 18.65, 18.8), Word("tuyết", 19.1, 19.4),
          Word("mưu", 19.45, 19.7), Word("này", 19.75, 19.95), Word("giá", 20.0, 20.2), Word("189K", 20.3, 20.9)]


def test_fix_with_phrase_start_time_matches_by_text():
    """I1: the agent only saw phrase times, so `at` is the phrase start (18.2), 0.9 s before the wrong word."""
    tw = map_words([Range(18.0, 21.0)], PHRASE, [CaptionFix(18.2, "tuyết mưu", "tuyết mưa")], [])
    texts = [w.text for w in tw]
    assert "tuyết mưa" in texts and "tuyết" not in texts and "mưu" not in texts


def test_emphasis_far_from_at_falls_back_to_unique_text_match():
    tw = map_words([Range(18.0, 21.0)], PHRASE, [], [Emphasis(18.2, "189k")])
    assert next(w for w in tw if w.text == "189K").emph


def test_fix_picks_nearest_occurrence_and_checks_every_word():
    words = [Word("son", 1.0, 1.3), Word("kem", 1.4, 1.7), Word("son", 5.0, 5.3), Word("môi", 5.4, 5.7)]
    tw = map_words([Range(0.9, 6.0)], words, [CaptionFix(5.2, "son", "SON")], [])
    assert [w.text for w in tw] == ["son", "kem", "SON", "môi"]
    # multi-word fix whose second word does not match is not applied
    tw = map_words([Range(0.9, 6.0)], words, [CaptionFix(1.0, "son môi", "X")], [])
    assert [w.text for w in tw][:2] == ["son", "kem"]


def test_unmatched_fix_reported_in_notes():
    from autoedit.edl import validate_edl
    edl, notes = validate_edl({"keep": [{"start": 18.0, "end": 21.0}],
                               "caption_fixes": [{"at": 18.2, "wrong": "không có", "right": "X"},
                                                 {"at": 18.2, "wrong": "tuyết mưu", "right": "tuyết mưa"}],
                               "emphasis": [{"at": 20.0, "word": "zzz"}]}, PHRASE, 25.0)
    assert any("không có" in n for n in notes) and any("zzz" in n for n in notes)
    assert not any("tuyết mưu" in n for n in notes)


def test_reversed_ranges_words_in_output_order():
    """B2: keep order [5.0-6.4] then [0.9-1.8]: the later words play first; cues stay in output-time order."""
    ranges = [Range(4.9, 6.4), Range(0.9, 1.8)]
    tw = map_words(ranges, WORDS, [], [])
    assert [w.text for w in tw] == ["son", "này", "giá", "189K", "chào", "cả", "nhà"]
    assert all(a.start <= b.start for a, b in zip(tw, tw[1:]))
    cues = build_cues(ranges, WORDS, [], [], total=2.4)
    assert all(a.end <= b.start + 1e-9 for a, b in zip(cues, cues[1:]))
    assert cues[0].words[0].text == "son" and cues[-1].words[-1].text == "nhà"
    assert abs(next(w for w in tw if w.text == "chào").start - (1.0 - 0.9 + 1.5)) < 1e-6
