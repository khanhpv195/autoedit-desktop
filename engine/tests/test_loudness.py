from autoedit.render.loudness import loudnorm, measure


def test_two_pass_hits_target(clip, tmp_path):
    out = loudnorm(clip, tmp_path / "n.mp4", two_pass=True)
    m = measure(out)
    assert m is not None and abs(float(m["input_i"]) - (-14.0)) <= 1.0


def test_one_pass_runs(clip, tmp_path):
    assert loudnorm(clip, tmp_path / "p.mp4", two_pass=False).stat().st_size > 0
