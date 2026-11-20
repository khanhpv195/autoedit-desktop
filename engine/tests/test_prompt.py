import pytest
from autoedit.agent.prompt import build_edit_message, build_edit_prompt
from autoedit.resources import agent_dir
from autoedit.prep import Prepared
from autoedit.prep.probe import MediaInfo
from autoedit.project import Project
from autoedit.transcript import Word


def test_prompt_contents(tmp_path):
    proj = Project(dir=tmp_path, niche="thoi-trang", clip="c.mp4", logo="l.png",
                   script_card={"title": "x"})
    prep = Prepared(info=MediaInfo(duration=20, width=1080, height=1920, fps=30, hdr=False, has_audio=True),
                    normalized=tmp_path / "n.mp4", words=[Word("a", 0, 1)], keyframes=[])
    p = build_edit_prompt(proj, prep, "gọn", "ngắn hơn", {"keep": []})
    assert "Thời trang" in p and "Customer request: gọn" in p and "Logo: yes" in p
    assert "has speech" in p and "ngắn hơn" in p and "Previous EDL" in p and "Chosen script card" in p
    assert "choose the strongest" in build_edit_prompt(proj, prep, " ", None, None)


def _prep(tmp_path, n_frames=6):
    from PIL import Image
    kfs = []
    for i in range(n_frames):
        p = tmp_path / f"kf_{i}.jpg"; Image.new("RGB", (54, 96), "red").save(p); kfs.append(p)
    words = [Word("chị", 1.0, 1.2), Word("giá", 1.3, 1.5), Word("189K", 1.6, 2.2)]
    return Prepared(info=MediaInfo(duration=12, width=1080, height=1920, fps=30, hdr=False, has_audio=True),
                    normalized=tmp_path / "n.mp4", words=words, keyframes=kfs)


def test_first_message_has_transcript_skills_words_and_frames(tmp_path):
    proj = Project(dir=tmp_path, niche="my-pham", clip="c.mp4")
    m = build_edit_message(proj, _prep(tmp_path), "gọn", None, None, agent_dir())
    assert m["type"] == "user" and m["parent_tool_use_id"] is None and m["session_id"] == "default"
    content = m["message"]["content"]
    text = content[0]["text"]
    assert "Customer request: gọn" in text
    assert "[1.00-2.20] chị giá 189K" in text                      # phrase transcript
    assert "[1.60] 189K" in text and "[1.30] giá" in text             # word times (I1)
    assert "## Skill: video-use" in text and "Cut craft" in text       # video-use body
    assert "## Skill: edit-video" in text and "Whisper quirks" in text
    assert "## Skill: niche-hooks (my-pham)" in text and "Swatch thật" in text   # niche section
    assert "name: video-use" not in text and "description:" not in text   # frontmatter stripped
    assert "## thoi-trang" not in text and "## do-an" not in text         # only this niche
    images = [c for c in content if c["type"] == "image"]
    assert len(images) == 6 and images[0]["source"]["media_type"] == "image/jpeg"
    labels = [c["text"] for c in content[1:] if c["type"] == "text"]
    assert labels[0] == "Keyframe at 1.00s" and labels[5] == "Keyframe at 11.00s"


def test_message_without_keyframes_or_speech(tmp_path):
    proj = Project(dir=tmp_path, niche="chung", clip="c.mp4")
    prep = _prep(tmp_path, 0)
    prep.words = []
    m = build_edit_message(proj, prep, "", None, None, agent_dir())
    assert len(m["message"]["content"]) == 1 and "(no speech)" in m["message"]["content"][0]["text"]
