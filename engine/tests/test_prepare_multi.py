import io
import json

import pytest
from PIL import Image

import autoedit.prep as prep
from autoedit.errors import BadInput
from autoedit.events import Emitter
from autoedit.prep import prepare
from autoedit.prep.probe import check_image, check_total_duration, probe
from autoedit.project import Project
from autoedit.transcript import Word


def _project(tmp_path, clip, landscape_clip, images=()):
    d = tmp_path / "proj"
    (d / "input").mkdir(parents=True)
    (d / "input" / "a.mp4").write_bytes(clip.read_bytes())
    (d / "input" / "b.mp4").write_bytes(landscape_clip.read_bytes())
    for n in images:
        Image.new("RGB", (1600, 900), (200, 30, 30)).save(d / "input" / n)
    (d / "project.json").write_text(json.dumps(
        {"niche": "chung", "clips": ["a.mp4", "b.mp4"], "images": list(images)}))
    return d


def test_multi_clip_prepare_spans_cache_and_images(clip, landscape_clip, tmp_path, monkeypatch):
    d = _project(tmp_path, clip, landscape_clip, images=["p.png"])
    seen = []
    monkeypatch.setattr(prep, "transcribe", lambda v, wd: seen.append(v) or [Word("a", 0.1, 0.4)])
    norm_calls = []
    real = prep.normalize
    monkeypatch.setattr(prep, "normalize", lambda *a: norm_calls.append(1) or real(*a))
    concat_calls = []
    real_c = prep.concat
    monkeypatch.setattr(prep, "concat", lambda *a: concat_calls.append(1) or real_c(*a))
    buf = io.StringIO()
    p1 = prepare(Project.load(d), Emitter(buf))
    assert p1.normalized == d / "work" / "source.mp4" == p1.timeline
    assert [s[0] for s in p1.spans] == ["a.mp4", "b.mp4"]
    assert p1.spans[0][1] == 0.0 and abs(p1.spans[0][2] - 6.0) < 0.2
    assert abs(p1.spans[1][1] - p1.spans[0][2]) < 1e-6
    assert abs(p1.spans[1][2] - p1.info.duration) < 0.01 and abs(p1.info.duration - 10.0) < 0.4
    assert (p1.info.width, p1.info.height) == (1080, 1920)
    assert len(p1.keyframes) == 6 and len(p1.images) == 1
    img = p1.images[0]
    assert img.name == "p.png" and img.path == d / "input" / "p.png" and max(Image.open(img.small).size) <= 768
    prepare(Project.load(d), Emitter(buf))
    assert len(norm_calls) == 2 and len(concat_calls) == 1       # everything cached on the second run
    assert seen[0] == seen[1] == p1.normalized


def test_changing_clip_order_rebuilds_timeline_and_frames(clip, landscape_clip, tmp_path, monkeypatch):
    d = _project(tmp_path, clip, landscape_clip)
    monkeypatch.setattr(prep, "transcribe", lambda v, wd: [])
    p1 = prepare(Project.load(d), Emitter(io.StringIO()))
    before = [f.read_bytes() for f in p1.keyframes]
    data = json.loads((d / "project.json").read_text())
    data["clips"] = ["b.mp4", "a.mp4"]
    (d / "project.json").write_text(json.dumps(data))
    p2 = prepare(Project.load(d), Emitter(io.StringIO()))
    assert [s[0] for s in p2.spans] == ["b.mp4", "a.mp4"]
    assert abs(p2.spans[0][2] - 4.0) < 0.2
    assert [f.read_bytes() for f in p2.keyframes] != before


def test_total_duration_limit():
    check_total_duration(600)
    with pytest.raises(BadInput, match="600"):
        check_total_duration(601)


def test_check_image(tmp_path):
    ok = tmp_path / "a.png"
    Image.new("RGB", (30, 20)).save(ok)
    assert check_image(ok) == (30, 20)
    bad = tmp_path / "b.png"
    bad.write_bytes(b"nope")
    with pytest.raises(BadInput):
        check_image(bad)
    with pytest.raises(BadInput):
        check_image(tmp_path / "c.gif")


def test_concat_is_stream_copy_of_uniform_clips(clip, landscape_clip, tmp_path):
    from autoedit.prep.normalize import concat, normalize
    parts = []
    for i, c in enumerate((clip, landscape_clip)):
        out = tmp_path / f"{i}.mp4"
        normalize(c, out, probe(c))
        parts.append(out)
    joined = concat(parts, tmp_path / "j.mp4")
    assert abs(probe(joined).duration - sum(probe(p).duration for p in parts)) < 0.3


def _stub(monkeypatch):
    monkeypatch.setattr(prep, "transcribe", lambda v, wd: [Word("a", 0.1, 0.4)])
    calls = []
    real = prep.normalize
    monkeypatch.setattr(prep, "normalize", lambda *a: calls.append(a[0].name) or real(*a))
    return calls


def test_reordering_clips_reuses_normalized_cache_and_drops_legacy(clip, landscape_clip, tmp_path, monkeypatch):
    d = _project(tmp_path, clip, landscape_clip)
    calls = _stub(monkeypatch)
    (d / "work").mkdir()
    (d / "work" / "normalized.mp4").write_bytes(b"old")
    (d / "work" / "normalized.json").write_text("{}")
    prepare(Project.load(d), Emitter(io.StringIO()))
    assert sorted(calls) == ["a.mp4", "b.mp4"]
    assert not (d / "work" / "normalized.mp4").exists() and not (d / "work" / "normalized.json").exists()
    data = json.loads((d / "project.json").read_text())
    data["clips"] = ["b.mp4", "a.mp4"]
    (d / "project.json").write_text(json.dumps(data))
    calls.clear()
    p = prepare(Project.load(d), Emitter(io.StringIO()))
    assert calls == [] and [s[0] for s in p.spans] == ["b.mp4", "a.mp4"]
    assert len(list((d / "work" / "norm").glob("*.mp4"))) == 2
    data["clips"] = ["b.mp4"]
    (d / "project.json").write_text(json.dumps(data))
    prepare(Project.load(d), Emitter(io.StringIO()))
    assert len(list((d / "work" / "norm").glob("*.mp4"))) == 1       # unused entry cleaned


def test_image_thumbnail_cache_is_fingerprinted(clip, landscape_clip, tmp_path, monkeypatch):
    import os
    d = _project(tmp_path, clip, landscape_clip, images=["sp.png"])
    _stub(monkeypatch)

    def run():
        return prepare(Project.load(d), Emitter(io.StringIO())).images[0]

    def color(img):
        with Image.open(img.small) as im:
            return im.getpixel((5, 5))

    first = run()
    assert color(first)[0] > 150                                   # red
    # same name, new content, OLDER mtime (e.g. a copy that keeps its timestamp)
    src = d / "input" / "sp.png"
    old = src.stat().st_mtime - 1000
    Image.new("RGB", (1600, 900), (10, 10, 240)).save(src)
    os.utime(src, (old, old))
    assert color(run())[2] > 150                                   # blue now
    # sp.png replaced by sp.jpg at the same index
    Image.new("RGB", (1600, 900), (10, 240, 10)).save(d / "input" / "sp.jpg")
    src.unlink()
    data = json.loads((d / "project.json").read_text())
    data["images"] = ["sp.jpg"]
    (d / "project.json").write_text(json.dumps(data))
    third = run()
    assert color(third)[1] > 150 and third.name == "sp.jpg"
    assert len(list((d / "work" / "images").glob("*.jpg"))) == 1
