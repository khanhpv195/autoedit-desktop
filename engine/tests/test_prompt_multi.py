from PIL import Image

from autoedit.agent.analyze import build_analyze_message
from autoedit.agent.prompt import build_edit_message, build_edit_prompt
from autoedit.prep import Prepared, PreparedImage
from autoedit.prep.probe import MediaInfo
from autoedit.project import Project
from autoedit.resources import agent_dir
from autoedit.transcript import Word


def _prep(tmp_path):
    kf = tmp_path / "kf_0.jpg"
    Image.new("RGB", (54, 96), "red").save(kf)
    small = tmp_path / "s.jpg"
    Image.new("RGB", (96, 54), "blue").save(small)
    return Prepared(
        info=MediaInfo(duration=16.4, width=1080, height=1920, fps=30, hdr=False, has_audio=True),
        normalized=tmp_path / "source.mp4", words=[Word("chị", 1.0, 1.2)], keyframes=[kf],
        spans=[("a.mp4", 0.0, 12.4), ("b.mp4", 12.4, 16.4)],
        images=[PreparedImage("giay.png", tmp_path / "giay.png", small, 1600, 900)])


def test_prompt_lists_spans_and_images(tmp_path):
    proj = Project(dir=tmp_path, niche="chung", clips=["a.mp4", "b.mp4"], images=["giay.png"])
    p = build_edit_prompt(proj, _prep(tmp_path), "", None, None)
    assert 'Clip 1 "a.mp4": 0.00-12.40s' in p and 'Clip 2 "b.mp4": 12.40-16.40s' in p
    assert '"giay.png"' in p and "broll" in p


def test_single_clip_prompt_has_no_span_list(tmp_path):
    proj = Project(dir=tmp_path, niche="chung", clips=["a.mp4"])
    prep = _prep(tmp_path)
    prep.spans, prep.images = [("a.mp4", 0.0, 16.4)], []
    p = build_edit_prompt(proj, prep, "", None, None)
    assert "Clip 1" not in p and "Images for b-roll" not in p


def test_message_attaches_labelled_images(tmp_path):
    proj = Project(dir=tmp_path, niche="chung", clips=["a.mp4", "b.mp4"], images=["giay.png"])
    content = build_edit_message(proj, _prep(tmp_path), "", None, None, agent_dir())["message"]["content"]
    idx = next(i for i, c in enumerate(content) if c["type"] == "text" and c["text"].startswith('Image "giay.png"'))
    assert content[idx + 1]["type"] == "image" and content[idx + 1]["source"]["media_type"] == "image/jpeg"
    assert sum(c["type"] == "image" for c in content) == 2


def test_analyze_message_mentions_spans_and_images(tmp_path):
    msg = build_analyze_message(_prep(tmp_path), "chung", agent_dir(), [])
    content = msg["message"]["content"]
    assert 'Clip 2 "b.mp4": 12.40-16.40s' in content[0]["text"]
    assert any(c["type"] == "text" and c["text"] == 'Image "giay.png"' for c in content)


def _many_images(tmp_path, n):
    from autoedit.prep.keyframes import contact_sheets  # noqa: F401
    imgs = []
    for i in range(n):
        small = tmp_path / f"s{i}.jpg"
        Image.new("RGB", (96, 54), (i * 10, 50, 50)).save(small)
        imgs.append(PreparedImage(f"sp_{i}.png", tmp_path / f"sp_{i}.png", small, 1600, 900))
    return imgs


def test_many_images_become_labelled_contact_sheets(tmp_path):
    prep = _prep(tmp_path)
    prep.images = _many_images(tmp_path, 20)
    proj = Project(dir=tmp_path, niche="chung", clips=["a.mp4", "b.mp4"], images=prep.image_names)
    content = build_edit_message(proj, prep, "", None, None, agent_dir())["message"]["content"]
    n_images = sum(c["type"] == "image" for c in content)
    assert n_images == 1 + 3 and n_images <= 24            # 1 keyframe + 3 sheets of up to 9 tiles
    texts = "\n".join(c["text"] for c in content if c["type"] == "text")
    assert "contact sheets" in texts and "broll.image" in texts
    assert '"sp_0.png"' in texts and '"sp_19.png"' in texts
    sheets = sorted((tmp_path / "sheets").glob("sheet_*.jpg"))
    assert len(sheets) == 3
    with Image.open(sheets[0]) as im:
        assert im.width == 900 and im.height > 900          # 3 columns of 300 px tiles
    # <= 8 images still go one by one
    prep.images = _many_images(tmp_path, 8)
    content = build_edit_message(proj, prep, "", None, None, agent_dir())["message"]["content"]
    assert sum(c["type"] == "image" for c in content) == 1 + 8
