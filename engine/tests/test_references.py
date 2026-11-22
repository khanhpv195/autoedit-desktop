import json

import pytest

from autoedit.agent import references as refs
from autoedit.agent.chat import build_chat_message
from autoedit.errors import BadInput
from autoedit.prep import Prepared
from autoedit.prep.probe import MediaInfo
from autoedit.project import Project, read_project_json
from autoedit.resources import agent_dir
from autoedit.transcript import Word


def make_project(tmp_path, name="Quần legging", niche="thoi-trang", folder="2026-11-22_abc"):
    d = tmp_path / folder
    (d / "input").mkdir(parents=True)
    (d / "input" / "a.mp4").write_bytes(b"x")
    (d / "input" / "b.mp4").write_bytes(b"x")
    run = {"n": 1, "final": "runs/1/final.mp4", "prompt": "60s, đưa chân vòng kiềng lên đầu", "feedback": None,
           "summary": ["Đưa câu chân vòng kiềng lên đầu"], "needs_review": False, "fallback": False}
    data = {"niche": niche, "clips": ["a.mp4", "b.mp4"], "name": name, "runs": [run], "target_seconds": [57, 63]}
    (d / "project.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (d / "runs" / "1").mkdir(parents=True)
    edl = {"keep": [{"start": 20.0, "end": 22.0}, {"start": 10.0, "end": 16.0}], "mute": [1],
           "broll": [{"shot": 3.0, "at": 12.0, "dur": 2.5}], "hook": {"text": "Chân vòng kiềng vẫn đẹp"}}
    (d / "runs" / "1" / "edl.json").write_text(json.dumps(edl, ensure_ascii=False), encoding="utf-8")
    return Project.load(d)


def prep(tmp_path):
    words = [Word("Quần", 10.2, 10.5), Word("legging", 10.5, 11.0), Word("đẹp", 11.0, 11.3),
             Word("vào", 17.0, 17.3), Word("trang", 17.3, 17.6), Word("cá", 17.6, 17.8), Word("nhân", 17.8, 18.0),
             Word("chân", 20.2, 20.5), Word("vòng", 20.5, 20.8), Word("kiềng", 20.8, 21.2)]
    return Prepared(info=MediaInfo(30, 1080, 1920, 30, False, True), normalized=tmp_path / "n.mp4", words=words,
                    keyframes=[], spans=[("a.mp4", 0.0, 10.0), ("b.mp4", 10.0, 30.0)])


def test_save_writes_the_reference_and_marks_the_run(tmp_path):
    p = make_project(tmp_path)
    meta = refs.save_reference(p, 1, prep(tmp_path), now=lambda: 100.0)
    assert meta["id"] == "2026-11-22_abc-run1" and meta["name"] == "Quần legging" and meta["run"] == 1
    body = (refs.refs_dir() / "2026-11-22_abc-run1.md").read_text(encoding="utf-8")
    assert '## Mẫu của khách: "Quần legging" (thoi-trang)' in body
    assert "- Clip 1: 0.0-10.0 s, no speech" in body and "- Clip 2: 10.0-30.0 s, speech 10.2-21.2 s" in body
    assert "- Customer request: 60s, đưa chân vòng kiềng lên đầu" in body and "Target length: 57-63 s" in body
    assert "[giữ] 10.2 Quần legging đẹp" in body and "[bỏ] 17.0 vào trang cá nhân" in body
    assert "[giữ] 20.2 chân vòng kiềng" in body and '"mute": [' in body
    assert read_project_json(p.dir)["runs"][0]["reference"] == "2026-11-22_abc-run1"
    assert refs.list_references() == [{"id": "2026-11-22_abc-run1", "name": "Quần legging", "niche": "thoi-trang",
                                       "project": str(p.dir), "run": 1, "saved_at": 100.0}]


def test_save_needs_an_existing_run_with_an_edl(tmp_path):
    p = make_project(tmp_path)
    with pytest.raises(BadInput):
        refs.save_reference(p, 2, prep(tmp_path))
    (p.dir / "runs" / "1" / "edl.json").unlink()
    with pytest.raises(BadInput):
        refs.save_reference(p, 1, prep(tmp_path))
    assert refs.list_references() == []


def test_delete_removes_the_file_and_the_mark(tmp_path):
    p = make_project(tmp_path)
    refs.save_reference(p, 1, prep(tmp_path))
    refs.delete_reference("2026-11-22_abc-run1")
    assert refs.list_references() == []
    assert "reference" not in read_project_json(p.dir)["runs"][0]
    refs.delete_reference("2026-11-22_abc-run1")          # already gone: no error
    with pytest.raises(BadInput):
        refs.delete_reference("../etc/passwd")


def test_prompt_text_has_saved_references_same_niche_first_and_never_the_project_itself(tmp_path):
    a = make_project(tmp_path, name="Váy A", folder="a")
    b = make_project(tmp_path, name="Son B", niche="my-pham", folder="b")
    c = make_project(tmp_path, name="Áo C", folder="c")
    t = iter([1.0, 2.0, 3.0])
    for p in (a, b, c):
        refs.save_reference(p, 1, prep(tmp_path), now=lambda: next(t))
    text = refs.reference_text(agent_dir(), "thoi-trang")
    assert "Clip-chuan" in text and "Mẫu khách đã lưu" in text
    assert text.index('"Áo C"') < text.index('"Váy A"') and '"Son B"' not in text     # 2 max, same niche, newest first
    text = refs.reference_text(agent_dir(), "thoi-trang", project_dir=c.dir)
    assert '"Áo C"' not in text and '"Váy A"' in text and '"Son B"' in text


def test_no_saved_references_means_only_the_built_in_one(tmp_path):
    text = refs.reference_text(agent_dir(), "thoi-trang")
    assert "Clip-chuan" in text and "Mẫu khách đã lưu" not in text


def test_chat_prompt_shows_saved_references(tmp_path):
    other = make_project(tmp_path, name="Váy A", folder="a")
    refs.save_reference(other, 1, prep(tmp_path))
    p = make_project(tmp_path, name="Mới", folder="new")
    text = build_chat_message(p, prep(tmp_path), [], "", agent_dir())["message"]["content"][0]["text"]
    assert '## Mẫu của khách: "Váy A"' in text


def test_cli_list_and_delete(tmp_path, capsys):
    from autoedit.cli import main
    p = make_project(tmp_path)
    refs.save_reference(p, 1, prep(tmp_path))
    assert main(["reference", "list"]) == 0
    ev = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert ev["type"] == "references" and [r["id"] for r in ev["references"]] == ["2026-11-22_abc-run1"]
    assert main(["reference", "delete", "--id", "2026-11-22_abc-run1"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == {"type": "references", "references": []}
