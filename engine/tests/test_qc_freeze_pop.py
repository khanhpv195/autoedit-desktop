import re
import subprocess

import pytest

from autoedit.render.qc import detect_freezes, edit_checks, pop_scores, run_qc


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


@pytest.fixture
def frozen_tail(tmp_path):
    """2 s of moving testsrc, then the last frame held for 1.5 s."""
    p = tmp_path / "frozen.mp4"
    _ff("-f", "lavfi", "-i", "testsrc=s=320x240:r=30:d=2", "-vf", "tpad=stop_mode=clone:stop_duration=1.5",
        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-an", str(p))
    return p


def _wav(path, expr, dur=2.0):
    _ff("-f", "lavfi", "-i", f"aevalsrc=exprs='{expr}':s=48000:d={dur}", "-c:a", "pcm_s16le", str(path))
    return path


def test_detect_freezes_finds_held_tail(frozen_tail):
    fr = detect_freezes(frozen_tail)
    assert len(fr) == 1
    s, e = fr[0]
    assert s == pytest.approx(2.0, abs=0.15) and e == pytest.approx(3.5, abs=0.15)


def test_freeze_is_an_issue_unless_broll_covers_it(frozen_tail):
    issues = edit_checks(frozen_tail, broll=[], cuts=[])
    assert len(issues) == 1 and re.fullmatch(r"khung đứng [12]\.\d\d–3\.50s", issues[0]), issues
    assert edit_checks(frozen_tail, broll=[(1.8, 3.6)], cuts=[]) == []


def test_moving_video_has_no_freeze(clip):
    assert detect_freezes(clip) == []


def test_pop_score_flags_discontinuity(tmp_path):
    # cosine flips sign at t=1: a jump of 1.0 between two samples
    p = _wav(tmp_path / "pop.wav", "if(lt(t,1),0.5*cos(2*PI*440*t),-0.5*cos(2*PI*440*t))")
    [(t, score)] = pop_scores(p, [1.0])
    assert t == 1.0 and score > 8
    issues = edit_checks(p, broll=[], cuts=[1.0], video=False)
    assert issues == ["tiếng bụp ở cắt 1.00s"]


def test_pop_score_smooth_sine_is_low(tmp_path):
    p = _wav(tmp_path / "smooth.wav", "0.5*sin(2*PI*440*t)")
    [(_, score)] = pop_scores(p, [1.0])
    assert score <= 8
    assert edit_checks(p, broll=[], cuts=[1.0], video=False) == []


def test_pop_on_silence_is_not_flagged(tmp_path):
    p = _wav(tmp_path / "quiet.wav", "if(lt(t,1),0,0.002*sin(2*PI*440*t))")
    assert edit_checks(p, broll=[], cuts=[1.0], video=False) == []


def test_run_qc_includes_freeze(frozen_tail):
    r = run_qc(frozen_tail, 3.5)
    assert not r.ok and any(i.startswith("khung đứng") for i in r.issues)
    assert run_qc(frozen_tail, 3.5, broll=[(1.9, 3.5)]).issues == [i for i in r.issues
                                                                   if not i.startswith("khung đứng")]
