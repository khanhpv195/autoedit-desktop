import io
import json

import pytest

from autoedit.agent import options, tools
from autoedit.agent.prompt import build_edit_prompt
from autoedit.agent.session import EditSession
from autoedit.edl import DEFAULT_CTA, validate_edl
from autoedit.events import Emitter
from autoedit.prep import Prepared
from autoedit.prep.probe import MediaInfo
from autoedit.project import Project
from autoedit.transcript import Word


def make(tmp_path, **over):
    (tmp_path / "input").mkdir(exist_ok=True)
    (tmp_path / "input" / "clip.mp4").write_bytes(b"x")
    data = {"niche": "chung", "clips": ["clip.mp4"]} | over
    (tmp_path / "project.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_legacy_project_loads_with_defaults(tmp_path):
    p = Project.load(make(tmp_path))
    assert p.voiceover is None and not p.voiceover_on
    assert p.product_info == "" and p.cta_text == DEFAULT_CTA and p.name == "" and p.target_seconds is None
    assert p.target_range() is None


def test_new_fields_load_and_save(tmp_path):
    vo = {"enabled": True, "voice_id": "v1", "voice_name": "Mai"}
    p = Project.load(make(tmp_path, voiceover=vo, product_info="Áo len 199K", cta_text="MUA NGAY", length="short",
                              name=" Quần ống rộng ", target_seconds=[40, 50]))
    assert p.voiceover_on and p.product_info == "Áo len 199K" and p.cta_text == "MUA NGAY"
    assert p.name == "Quần ống rộng" and p.target_range() == (40.0, 50.0)
    p.save()
    saved = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert saved["voiceover"] == vo and "length" not in saved and saved["cta_text"] == "MUA NGAY"
    assert saved["name"] == "Quần ống rộng" and saved["target_seconds"] == [40.0, 50.0]


@pytest.mark.parametrize("vo", [None, {"enabled": False, "voice_id": "v"}, {"enabled": True, "voice_id": ""}])
def test_voiceover_off_variants(tmp_path, vo):
    assert not Project.load(make(tmp_path, voiceover=vo)).voiceover_on


def test_bad_values_are_sanitized(tmp_path):
    p = Project.load(make(tmp_path, target_seconds=[50, 10], cta_text="x" * 31, product_info="a" * 600, name=7))
    assert p.target_seconds is None and p.cta_text == DEFAULT_CTA and len(p.product_info) == 500 and p.name == ""
    p2 = Project.load(make(tmp_path, cta_text="   ", product_info=None, target_seconds="30", name="x" * 90))
    assert p2.cta_text == DEFAULT_CTA and p2.product_info == "" and p2.target_seconds is None and len(p2.name) == 80


def test_target_priority(tmp_path):
    p = Project.load(make(tmp_path, prompt="cắt còn 30s"))
    assert p.target_range() == (27.0, 33.0)                         # from the saved prompt
    assert p.target_range("làm 60s") == (54.0, 66.0)               # from this request
    assert p.target_range("làm 60s", "dài quá, cắt còn 20s") == (18.0, 22.0)    # re-edit feedback wins
    p.target_seconds = [40.0, 45.0]
    assert p.target_range("làm 60s") == (40.0, 45.0)               # the confirmed plan beats the text
    assert p.target_range("", "dưới 30s") == (18.0, 30.0)


def test_default_model_is_sonnet():
    assert options.DEFAULT_MODEL == "claude-sonnet-5-5"


def _prep(tmp_path, dur=40.0, words=None):
    return Prepared(info=MediaInfo(duration=dur, width=1080, height=1920, fps=30, hdr=False, has_audio=True),
                    normalized=tmp_path / "n.mp4", words=[Word("a", 0, 1)] if words is None else words, keyframes=[])


def test_prompt_has_length_and_cta(tmp_path):
    proj = Project(dir=tmp_path, niche="chung", clips=["c.mp4"])
    p = build_edit_prompt(proj, _prep(tmp_path), "", None, None)
    assert "Target length: not given. Choose it from the content" in p and "and why in the first finish bullet" in p
    assert f"CTA text: {DEFAULT_CTA} (use it unless the customer request asks for another CTA)." in p
    proj.cta_text = "SĂN SALE"
    p = build_edit_prompt(proj, _prep(tmp_path), "cắt còn khoảng 1 phút", None, None)
    assert "Target length: 51–69s (the customer asked for it" in p and "CTA text: SĂN SALE" in p


def test_validate_edl_uses_default_cta():
    edl, _ = validate_edl({"keep": [{"start": 0.0, "end": 3.0}]}, [], 4.0, default_cta="MUA NGAY")
    assert edl.cta_text == "MUA NGAY"
    edl, _ = validate_edl({"keep": [{"start": 0.0, "end": 3.0}], "cta_text": " "}, [], 4.0, default_cta="MUA NGAY")
    assert edl.cta_text == "MUA NGAY"
    edl, _ = validate_edl({"keep": [{"start": 0.0, "end": 3.0}], "cta_text": "KHÁC"}, [], 4.0, default_cta="MUA NGAY")
    assert edl.cta_text == "KHÁC"


def _session(tmp_path, **over):
    proj = Project.load(make(tmp_path, **over))
    return EditSession(prepared=_prep(tmp_path, words=[]), project=proj, events=Emitter(io.StringIO()))


async def test_set_edl_length_note_and_project_cta(tmp_path):
    s = _session(tmp_path, cta_text="CHỐT ĐƠN")
    s.target = (20.0, 35.0)
    res = await tools.set_edl(s, {"edl": {"keep": [{"start": 2.0, "end": 12.0}]}})
    assert not res.get("is_error")
    msg = json.loads(res["content"][0]["text"])
    assert any("Lưu ý: video dài 10.0s, khách muốn 20–35s" in n for n in msg["notes"])
    assert s.edl.cta_text == "CHỐT ĐƠN"


async def test_set_edl_no_length_note_inside_range(tmp_path):
    s = _session(tmp_path)
    s.target = (20.0, 35.0)
    res = await tools.set_edl(s, {"edl": {"keep": [{"start": 2.0, "end": 27.0}]}})
    msg = json.loads(res["content"][0]["text"])
    assert not any("Lưu ý" in n for n in msg["notes"])


async def test_set_edl_no_length_note_without_target(tmp_path):
    s = _session(tmp_path)
    res = await tools.set_edl(s, {"edl": {"keep": [{"start": 2.0, "end": 4.0}]}})
    msg = json.loads(res["content"][0]["text"])
    assert not any("Lưu ý" in n for n in msg["notes"])
