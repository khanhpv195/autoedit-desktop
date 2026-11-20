import subprocess
from autoedit.render.loudness import loudnorm
from autoedit.render.qc import run_qc


def test_good_file_passes(clip, tmp_path):
    out = loudnorm(clip, tmp_path / "n.mp4", two_pass=True)
    r = run_qc(out, 6.0)
    assert r.ok, r.issues


def test_wrong_duration_and_loudness_fail(clip):
    r = run_qc(clip, 9.0)
    assert not r.ok and any("thời lượng" in i for i in r.issues)


def test_black_frames_fail(tmp_path):
    p = tmp_path / "black.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=black:s=540x960:r=30:d=2",
                    "-f", "lavfi", "-i", "sine=d=2", "-shortest", "-pix_fmt", "yuv420p", str(p)], check=True)
    r = run_qc(loudnorm(p, tmp_path / "b.mp4", True), 2.0)
    assert any("khung đen" in i for i in r.issues)
