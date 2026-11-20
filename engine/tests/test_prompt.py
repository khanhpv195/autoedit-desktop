from autoedit.agent.prompt import build_edit_prompt
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
