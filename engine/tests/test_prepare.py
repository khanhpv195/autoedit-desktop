import io, json
from autoedit.events import Emitter
from autoedit.prep import prepare
from autoedit.prep.keyframes import extract_keyframes, frame_at
from autoedit.project import Project
from autoedit.transcript import Word


def test_keyframes(clip, tmp_path):
    frames = extract_keyframes(clip, tmp_path / "f", 6.0, n=3)
    assert [f.name for f in frames] == ["kf_0.jpg", "kf_1.jpg", "kf_2.jpg"]
    assert all(f.stat().st_size > 1000 for f in frames)


def test_frame_at_width(clip, tmp_path):
    from PIL import Image
    p = frame_at(clip, 1.0, tmp_path / "x.jpg", width=270)
    with Image.open(p) as im:
        assert im.size[0] == 270


def test_prepare_caches_normalize(clip, tmp_path, monkeypatch):
    d = tmp_path / "proj"; (d / "input").mkdir(parents=True)
    (d / "input" / "clip.mp4").write_bytes(clip.read_bytes())
    (d / "project.json").write_text(json.dumps({"niche": "chung", "clip": "clip.mp4"}))
    import autoedit.prep as prep
    monkeypatch.setattr(prep, "transcribe", lambda v, wd: [Word("a", 0.1, 0.4)])
    calls = []
    real = prep.normalize
    monkeypatch.setattr(prep, "normalize", lambda *a: calls.append(1) or real(*a))
    buf = io.StringIO()
    p1 = prepare(Project.load(d), Emitter(buf))
    p2 = prepare(Project.load(d), Emitter(buf))
    assert len(calls) == 1
    assert p1.normalized == d / "work" / "normalized.mp4" and len(p2.keyframes) == 6
    assert '"type": "step"' in buf.getvalue()
