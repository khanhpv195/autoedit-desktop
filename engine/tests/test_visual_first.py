from PIL import Image

from autoedit.agent.analyze import INSTRUCTIONS, BROLL_IMAGES, build_analyze_message
from autoedit.agent.prompt import build_edit_message
from autoedit.prep import Prepared
from autoedit.prep.probe import MediaInfo
from autoedit.project import Project
from autoedit.resources import agent_dir
from autoedit.transcript import Word

VO = {"enabled": True, "voice_id": "v1", "voice_name": "Mai"}


def _prep(tmp_path, words):
    kf = tmp_path / "kf_0.jpg"
    Image.new("RGB", (54, 96), "red").save(kf)
    return Prepared(info=MediaInfo(duration=20, width=1080, height=1920, fps=30, hdr=False, has_audio=True),
                    normalized=tmp_path / "n.mp4", words=words, keyframes=[kf])


def _text(msg):
    return msg["message"]["content"][0]["text"]


def test_skill_file_has_frontmatter_and_editor_rules():
    t = (agent_dir() / ".claude" / "skills" / "visual-first" / "SKILL.md").read_text(encoding="utf-8")
    assert t.startswith("---\nname: visual-first\ndescription:")
    assert "self_eval" not in t and "move_to_front" in t and "1,5–4s" in t


def test_no_speech_prompt_has_visual_first(tmp_path):
    proj = Project(dir=tmp_path, niche="thoi-trang", clips=["c.mp4"])
    t = _text(build_edit_message(proj, _prep(tmp_path, []), "", None, None, agent_dir()))
    assert "## Skill: visual-first" in t and "Dựng theo hình" in t and "name: visual-first" not in t


def test_speech_prompt_without_voiceover_has_no_visual_first(tmp_path):
    proj = Project(dir=tmp_path, niche="thoi-trang", clips=["c.mp4"])
    t = _text(build_edit_message(proj, _prep(tmp_path, [Word("a", 0, 1)]), "", None, None, agent_dir()))
    assert "Dựng theo hình" not in t


def test_speech_prompt_with_voiceover_has_short_section(tmp_path):
    proj = Project(dir=tmp_path, niche="thoi-trang", clips=["c.mp4"], voiceover=VO)
    t = _text(build_edit_message(proj, _prep(tmp_path, [Word("a", 0, 1)]), "", None, None, agent_dir()))
    assert "Khi lời thoại yếu hoặc bật lồng tiếng:" in t and "Dựng theo hình" in t


def test_analyze_instructions_follow_editor_rules():
    for s in ("một video", "thứ tự", "5 từ", "2.5", "1.5–4", "3 s", "s cuối", "không bịa"):
        assert s in INSTRUCTIONS + BROLL_IMAGES, s


def test_analyze_message_has_length_visual_hint_and_product_info(tmp_path):
    proj = Project(dir=tmp_path, niche="thoi-trang", clips=["c.mp4"], length="short", voiceover=VO,
                   product_info="Áo len cổ lọ, 199K")
    t = _text(build_analyze_message(_prep(tmp_path, []), "thoi-trang", agent_dir(), [], project=proj))
    assert "15–20s" in t and "Áo len cổ lọ, 199K" in t and "Lồng tiếng AI: bật" in t
    assert "Dựng theo hình" in t or "visual-first" in t
    proj2 = Project(dir=tmp_path, niche="thoi-trang", clips=["c.mp4"])
    t2 = _text(build_analyze_message(_prep(tmp_path, [Word("a", 0, 1)]), "thoi-trang", agent_dir(), [], project=proj2))
    assert "20–35s" in t2 and "Lồng tiếng AI" not in t2 and "visual-first" not in t2
