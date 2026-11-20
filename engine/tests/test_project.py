import json
import pytest
from autoedit.project import Project, NICHES
from autoedit.errors import BadInput


def make(tmp_path, **over):
    (tmp_path / "input").mkdir()
    (tmp_path / "input" / "clip.mp4").write_bytes(b"x")
    data = {"niche": "my-pham", "clip": "clip.mp4", "logo": None, "music": None,
            "prompt": "", "script_card": None, "runs": []} | over
    (tmp_path / "project.json").write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def test_load_and_paths(tmp_path):
    p = Project.load(make(tmp_path))
    assert p.niche == "my-pham"
    assert p.clip_path == tmp_path / "input" / "clip.mp4"
    assert p.logo_path is None
    assert p.work_dir == tmp_path / "work" and p.work_dir.is_dir()


def test_bad_niche(tmp_path):
    with pytest.raises(BadInput):
        Project.load(make(tmp_path, niche="xe-hoi"))


def test_missing_clip(tmp_path):
    d = make(tmp_path)
    (d / "input" / "clip.mp4").unlink()
    with pytest.raises(BadInput):
        Project.load(d)


def test_new_run_dir_increments(tmp_path):
    p = Project.load(make(tmp_path))
    assert p.new_run_dir().name == "1"
    assert p.new_run_dir().name == "2"


def test_save_roundtrip(tmp_path):
    p = Project.load(make(tmp_path))
    p.runs.append({"n": 1, "final": "runs/1/final.mp4"})
    p.save()
    assert Project.load(tmp_path).runs == [{"n": 1, "final": "runs/1/final.mp4"}]


def test_niches_constant():
    assert NICHES == ("thoi-trang", "my-pham", "do-an", "phu-kien", "chung")
