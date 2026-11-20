from autoedit.prep.normalize import build_filter, normalize, TONEMAP
from autoedit.prep.probe import MediaInfo, probe


def info(w, h, hdr=False):
    return MediaInfo(duration=5, width=w, height=h, fps=30, hdr=hdr, has_audio=True)


def test_portrait_scales_and_pads_no_upscale():
    f = build_filter(info(720, 1280))
    assert "scale=w='min(1080,iw)'" in f and "pad=1080:1920" in f
    assert "fps=30" in f and f.endswith("[v]")


def test_landscape_gets_blur_background():
    f = build_filter(info(1920, 1080))
    assert "boxblur" in f and "overlay=(W-w)/2:(H-h)/2" in f


def test_hdr_prepends_tonemap():
    assert build_filter(info(1080, 1920, hdr=True)).startswith(f"[0:v]{TONEMAP},")


def test_normalize_landscape_output(landscape_clip, tmp_path):
    out = normalize(landscape_clip, tmp_path / "n.mp4", probe(landscape_clip))
    i = probe(out)
    assert (i.width, i.height) == (1080, 1920) and round(i.fps) == 30 and i.has_audio
    assert abs(i.duration - 4.0) < 0.15


def test_normalize_adds_silent_audio(tmp_path):
    import subprocess
    src = tmp_path / "mute.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=2",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    out = normalize(src, tmp_path / "n.mp4", probe(src))
    assert probe(out).has_audio
