import json

import pytest

from autoedit.errors import BadInput
from autoedit.project import Project


def make(d, **over):
    (d / "input").mkdir(exist_ok=True)
    (d / "input" / "clip.mp4").write_bytes(b"x")
    data = {"niche": "my-pham", "clips": ["clip.mp4"], "images": [], "logo": None, "music": None,
            "prompt": "", "script_card": None, "runs": []} | over
    (d / "project.json").write_text(json.dumps(data), encoding="utf-8")
    return d


def test_legacy_clip_field(tmp_path):
    d = make(tmp_path)
    data = json.loads((d / "project.json").read_text())
    data.pop("clips")
    data["clip"] = "clip.mp4"
    (d / "project.json").write_text(json.dumps(data))
    p = Project.load(d)
    assert p.clips == ["clip.mp4"] and p.images == []
    p.save()
    saved = json.loads((d / "project.json").read_text())
    assert saved["clips"] == ["clip.mp4"] and "clip" not in saved and saved["images"] == []


def test_multi_clips_and_images(tmp_path):
    d = make(tmp_path, clips=["clip.mp4", "b.mov"], images=["i.png"])
    (d / "input" / "b.mov").write_bytes(b"x")
    (d / "input" / "i.png").write_bytes(b"x")
    p = Project.load(d)
    assert [x.name for x in p.clip_paths] == ["clip.mp4", "b.mov"]
    assert [x.name for x in p.image_paths] == ["i.png"]


def _many(tmp_path, sub, n_clips, n_images):
    d = tmp_path / sub
    d.mkdir()
    clips = [f"c{i}.mp4" for i in range(n_clips)]
    images = [f"i{i}.png" for i in range(n_images)]
    make(d, clips=clips, images=images)
    for n in clips + images:
        (d / "input" / n).write_bytes(b"x")
    return d


def test_missing_image_and_limits(tmp_path):
    with pytest.raises(BadInput, match="ảnh"):
        Project.load(make(tmp_path, images=["nope.png"]))
    with pytest.raises(BadInput, match="10"):
        Project.load(_many(tmp_path, "two", 11, 0))
    with pytest.raises(BadInput, match="20"):
        Project.load(_many(tmp_path, "three", 1, 21))
    Project.load(_many(tmp_path, "ok", 10, 20))
