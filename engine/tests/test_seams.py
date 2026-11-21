from array import array

from autoedit.edl import Edl, Hook, Range
from autoedit.render import seams
from autoedit.render.seams import SR, quietest, refine_ranges


def _signal(loud):
    """1 s of audio, loud (0.5) except the given quiet spans."""
    x = array("f", [0.5 if (k // 8) % 2 else -0.5 for k in range(SR)])
    for a, b in loud:
        for k in range(int(a * SR), int(b * SR)):
            x[k] = 0.0
    return x


def test_end_moves_forward_into_the_pause_after_a_clipped_syllable():
    x = _signal([(0.60, 0.65)])                 # the real pause is 60-65 ms after the word end whisper gave
    [r] = refine_ranges(x, [Range(0.2, 0.52)], 1.0)
    assert 0.59 <= r.end <= 0.66 and abs(r.start - 0.2) <= 0.1


def test_quiet_edge_stays_put():
    x = _signal([(0.45, 0.60)])
    assert abs(quietest(x, 0.47, 0.64, 0.52) - 0.52) < 0.011


def test_edges_never_cross_a_neighbour_range():
    x = _signal([(0.50, 0.56)])
    a, b = refine_ranges(x, [Range(0.1, 0.48), Range(0.49, 0.9)], 1.0)
    assert a.end <= b.start + 1e-9


def test_refine_edl_flattens_moved_hook_into_play_order(monkeypatch):
    monkeypatch.setattr(seams, "_pcm", lambda src, sr: _signal([]))
    edl = Edl(keep=[Range(0.0, 0.4), Range(0.6, 0.9)], hook=Hook(0.6, 0.9, "HI"))
    out = seams.refine_edl(edl, "x", 1.0)
    assert out.hook.text == "HI" and not out.hook.moved and len(out.keep) == 2
    assert abs(out.keep[0].start - 0.6) <= 0.1


def test_edge_inside_speech_looks_wider_for_a_pause():
    x = _signal([(0.28, 0.33)])                 # the only pause is 200 ms before the start the snap gave
    [r] = refine_ranges(x, [Range(0.5, 0.9)], 1.0)
    assert 0.27 <= r.start <= 0.34
