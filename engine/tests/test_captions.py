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
