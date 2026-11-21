import json
from autoedit.edl import validate_edl
from autoedit.prep import Prepared
from autoedit.prep.probe import probe
from autoedit.project import Project
from autoedit.render.pipeline import render, preview_frames
from autoedit.transcript import Word

WORDS = [Word("chào", 0.6, 1.0), Word("cả", 1.05, 1.3), Word("nhà", 1.35, 1.8),
         Word("giá", 3.2, 3.6), Word("189K", 3.7, 4.4)]


def setup(tmp_path, clip):
    d = tmp_path / "p"; (d / "input").mkdir(parents=True)
    (d / "input" / "clip.mp4").write_bytes(clip.read_bytes())
    (d / "project.json").write_text(json.dumps({"niche": "my-pham", "clips": ["clip.mp4"]}))
    proj = Project.load(d)
    prep = Prepared(info=probe(clip), normalized=proj.clip_paths[0], words=WORDS, keyframes=[])
    edl, _ = validate_edl({"keep": [{"start": 0.6, "end": 1.8}, {"start": 3.2, "end": 4.4}],
                           "hook": {"move_to_front": [3.7, 4.4], "text": "CHỈ 189K"}}, WORDS, 6.0)
    return proj, prep, edl


def test_final_render_passes_qc(tmp_path, clip):
    proj, prep, edl = setup(tmp_path, clip)
    res = render(prep, proj, edl, tmp_path / "final.mp4", preview=False)
    assert res.qc.ok, res.qc.issues
    assert not res.needs_review and abs(res.duration - edl.output_duration()) < 0.1


def test_preview_and_frames(tmp_path, clip):
    proj, prep, edl = setup(tmp_path, clip)
    res = render(prep, proj, edl, tmp_path / "preview.mp4", preview=True)
    assert res.qc is None and probe(res.path).width == 540
    frames = preview_frames(res.path, edl, tmp_path / "pf")
    assert 2 <= len(frames) <= 4
