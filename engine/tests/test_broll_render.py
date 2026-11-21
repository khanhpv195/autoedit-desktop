import json

from PIL import Image

from autoedit.edl import validate_edl
from autoedit.prep import Prepared, PreparedImage
from autoedit.prep.keyframes import frame_at
from autoedit.prep.probe import probe
from autoedit.project import Project
from autoedit.render import compose as compose_mod
from autoedit.render.captions import Cue, TimedWord, write_ass
from autoedit.render.compose import compose
from autoedit.render.pipeline import render
from autoedit.transcript import Word

WORDS = [Word("chào", 0.6, 1.0), Word("cả", 1.05, 1.3), Word("nhà", 1.35, 1.8),
         Word("giá", 3.2, 3.6), Word("189K", 3.7, 4.4)]


def _graph(monkeypatch, tmp_path, base, **kw):
    seen = {}
    monkeypatch.setattr(compose_mod.bins, "run", lambda cmd, **k: seen.update(cmd=cmd))
    ass = write_ass([Cue(0.2, 1.0, [TimedWord("a", 0.2, 1.0, 0.2, 0)])], tmp_path / "c.ass")
    compose(base, tmp_path / "o.mp4", duration=8.0, ass=ass, hook_png=tmp_path / "h.png", logo_png=tmp_path / "l.png",
            cta_png=tmp_path / "c.png", music=None, speech=[], duck_db=-14, **kw)
    cmd = seen["cmd"]
    return cmd[cmd.index("-filter_complex") + 1].split(";"), cmd


def test_graph_has_broll_before_subtitles_and_subtitles_last(monkeypatch, tmp_path):
    broll = [(tmp_path / "a.jpg", 3.0, 5.0), (tmp_path / "b.jpg", 6.0, 7.5)]
    graph, cmd = _graph(monkeypatch, tmp_path, tmp_path / "b.mp4", preview=False, broll=broll)
    assert graph[-1].startswith("[") and "subtitles=" in graph[-1]
    overlays = [i for i, g in enumerate(graph) if "overlay=x=0:y=0" in g]
    assert len(overlays) == 2 and all(i < len(graph) - 1 for i in overlays)
    assert "between(t,3.000,5.000)" in graph[overlays[0]] and "between(t,6.000,7.500)" in graph[overlays[1]]
    assert any("zoompan" in g and "1.06" not in g and "0.06" in g for g in graph)
    hook_i = next(i for i, g in enumerate(graph) if "between(t,0,2.5)" in g)
    assert overlays[1] < hook_i                         # b-roll sits under hook, logo, CTA
    assert str(tmp_path / "a.jpg") in cmd and str(tmp_path / "b.jpg") in cmd


def test_preview_scales_broll_to_540p(monkeypatch, tmp_path):
    graph, _ = _graph(monkeypatch, tmp_path, tmp_path / "b.mp4", preview=True, broll=[(tmp_path / "a.jpg", 3.0, 5.0)])
    assert any("s=540x960" in g for g in graph)


def _setup(tmp_path, clip, broll):
    d = tmp_path / "p"
    (d / "input").mkdir(parents=True)
    (d / "input" / "clip.mp4").write_bytes(clip.read_bytes())
    Image.new("RGB", (1600, 900), (255, 0, 0)).save(d / "input" / "red.png")
    (d / "project.json").write_text(json.dumps({"niche": "my-pham", "clips": ["clip.mp4"], "images": ["red.png"]}))
    proj = Project.load(d)
    small = d / "work" / "s.jpg"
    Image.new("RGB", (96, 54)).save(small)
    prep = Prepared(info=probe(clip), normalized=proj.clip_paths[0], words=WORDS, keyframes=[],
                    spans=[("clip.mp4", 0.0, 6.0)],
                    images=[PreparedImage("red.png", proj.image_paths[0], small, 1600, 900)])
    edl, notes = validate_edl({"keep": [{"start": 0.0, "end": 6.0}],
                               "hook": {"move_to_front": [3.7, 4.4], "text": "CHỈ 189K"}, "broll": broll},
                              WORDS, 6.0, image_names=["red.png"])
    return proj, prep, edl


def test_render_overlays_image_only_inside_window(tmp_path, clip):
    # timeline 1.0 is output ~ 0.7(hook)+... ; pick a b-roll inside the 0.6-1.8 range after the hook
    proj, prep, edl = _setup(tmp_path, clip, [{"image": "red.png", "at": 2.0, "dur": 1.5}])
    assert len(edl.broll) == 1
    start, end = edl.output_span(edl.broll[0].at, edl.broll[0].dur)
    assert start >= 2.5
    out = tmp_path / "pv.mp4"
    res = render(prep, proj, edl, out, preview=True)
    assert abs(res.duration - edl.output_duration()) < 0.1

    def redness(t):
        from PIL import Image as I
        im = I.open(frame_at(out, t, tmp_path / f"f{t:.2f}.jpg", width=135)).convert("RGB")
        px = im.getpixel((im.width // 2, im.height // 2))
        return px[0] > 200 and px[1] < 80 and px[2] < 80

    assert redness((start + end) / 2)
    assert not redness(max(0.1, start - 0.3)) and not redness(min(res.duration - 0.1, end + 0.3))


def test_render_with_video_cutaway(tmp_path, clip):
    proj, prep, _ = _setup(tmp_path, clip, [])
    edl, notes = validate_edl({"keep": [{"start": 2.0, "end": 6.0}], "broll": [{"shot": 0.1, "at": 4.6, "dur": 1.5}]},
                              WORDS, 6.0, image_names=["red.png"], spans=prep.spans)
    assert edl.broll and edl.broll[0].shot == 0.1, notes
    res = render(prep, proj, edl, tmp_path / "pv.mp4", preview=True)
    assert abs(res.duration - edl.output_duration()) < 0.1
    assert (proj.work_dir / "render_preview" / "cut_0.mov").exists()
