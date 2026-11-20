import pytest
from autoedit.prep.probe import probe, check_clip, check_logo, check_music, MAX_CLIP_SECONDS
from autoedit.errors import BadInput


def test_probe_portrait(clip):
    info = probe(clip)
    assert info.width == 1080 and info.height == 1920 and info.portrait
    assert abs(info.duration - 6.0) < 0.1
    assert round(info.fps) == 30 and info.has_audio and not info.hdr


def test_probe_landscape(landscape_clip):
    assert not probe(landscape_clip).portrait


def test_rotation_swaps_dimensions(landscape_clip, tmp_path):
    import subprocess
    rotated = tmp_path / "rot.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-display_rotation", "90", "-i", str(landscape_clip),
                    "-c", "copy", str(rotated)], check=True)
    info = probe(rotated)
    assert (info.width, info.height) == (1080, 1920)


def test_check_clip_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.mp4"; bad.write_bytes(b"not a video")
    with pytest.raises(BadInput):
        check_clip(bad)


def test_check_clip_rejects_too_long(clip, monkeypatch):
    import autoedit.prep.probe as m
    monkeypatch.setattr(m, "MAX_CLIP_SECONDS", 5)
    with pytest.raises(BadInput):
        m.check_clip(clip)


def test_check_logo_and_music(tmp_path):
    from PIL import Image
    png = tmp_path / "logo.png"; Image.new("RGBA", (10, 10)).save(png)
    check_logo(png)
    with pytest.raises(BadInput):
        check_logo(tmp_path / "logo.gif")
    with pytest.raises(BadInput):
        check_music(tmp_path / "song.ogg")
