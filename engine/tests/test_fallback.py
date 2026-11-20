from autoedit.fallback import silence_cut_edl
from autoedit.transcript import Word


def test_cuts_long_silences_only():
    words = [Word("a", 0.5, 1.0), Word("b", 1.3, 1.8), Word("c", 3.0, 3.6)]  # gap 0.3 keep, gap 1.2 cut
    edl = silence_cut_edl(words, 5.0)
    assert len(edl.keep) == 2 and edl.hook is None
    assert edl.keep[0].end < 2.0 and edl.keep[1].start > 2.5


def test_no_speech_keeps_whole_clip():
    edl = silence_cut_edl([], 4.0)
    assert (edl.keep[0].start, edl.keep[0].end) == (0.0, 4.0)


def test_only_tiny_phrases_keeps_whole_clip():
    """M1: a lone 'ừ' (< 0.4 s) made validate_edl raise and the fallback crash."""
    edl = silence_cut_edl([Word("ừ", 1.0, 1.2)], 5.0)
    assert (edl.keep[0].start, edl.keep[0].end) == (0.0, 5.0)
