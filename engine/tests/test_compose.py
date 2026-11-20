import subprocess
from PIL import Image
from autoedit.edl import Range
from autoedit.prep.probe import probe
from autoedit.render.compose import compose, filter_path, music_volume_expr
from autoedit.render.captions import Cue, TimedWord, write_ass
from autoedit.render.segments import render_base


def test_filter_path_escapes():
    assert filter_path(__import__("pathlib").PureWindowsPath(r"C:\a b\c.ass")) == r"C\:/a b/c.ass"


def test_music_volume_expr():
    e = music_volume_expr([(0.0, 1.0), (2.0, 3.5)], duck_db=-14)
    assert "between(t,0.000,1.000)" in e and "between(t,2.000,3.500)" in e
    assert music_volume_expr([], -14).startswith("0.398")  # -8 dB


def _assets(tmp_path):
    hook = tmp_path / "hook.png"; Image.new("RGBA", (600, 140), (254, 44, 85, 255)).save(hook)
    logo = tmp_path / "logo.png"; Image.new("RGBA", (200, 100), (0, 0, 255, 255)).save(logo)
    music = tmp_path / "m.m4a"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=220:d=1.5", str(music)], check=True)
    ass = write_ass([Cue(0.2, 1.0, [TimedWord("chào", 0.2, 1.0, 0.2, 0)])], tmp_path / "c.ass")
    return hook, logo, music, ass


def test_compose_final(clip, tmp_path):
    base = render_base(clip, [Range(0.5, 1.9), Range(3.0, 5.5)], "chung", tmp_path, preview=False)
    hook, logo, music, ass = _assets(tmp_path)
    out = compose(base, tmp_path / "out.mp4", duration=3.9, ass=ass, hook_png=hook, logo_png=logo,
                  cta_png=hook, music=music, speech=[(0.2, 1.0)], duck_db=-14, preview=False)
    i = probe(out)
    assert abs(i.duration - 3.9) < 0.1 and (i.width, i.height) == (1080, 1920) and i.has_audio


def test_compose_preview_minimal(clip, tmp_path):
    base = render_base(clip, [Range(0.5, 1.9)], "chung", tmp_path, preview=True)
    _, _, _, ass = _assets(tmp_path)
    out = compose(base, tmp_path / "p.mp4", duration=1.4, ass=ass, hook_png=None, logo_png=None,
                  cta_png=None, music=None, speech=[], duck_db=-14, preview=True)
    assert (probe(out).width, probe(out).height) == (540, 960)
