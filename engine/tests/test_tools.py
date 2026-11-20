import base64, io, json
import pytest
from autoedit.agent import tools
from autoedit.agent.session import EditSession
from autoedit.events import Emitter
from autoedit.prep import Prepared
from autoedit.prep.probe import probe
from autoedit.project import Project
from autoedit.transcript import Word

WORDS = [Word("chào", 0.6, 1.0), Word("cả", 1.05, 1.3), Word("nhà", 1.35, 1.8),
         Word("giá", 3.2, 3.6), Word("189K", 3.7, 4.4)]
EDL = {"keep": [{"start": 0.6, "end": 1.8}, {"start": 3.2, "end": 4.4}]}


@pytest.fixture
def session(tmp_path, clip):
    d = tmp_path / "p"; (d / "input").mkdir(parents=True)
    (d / "input" / "clip.mp4").write_bytes(clip.read_bytes())
    (d / "project.json").write_text(json.dumps({"niche": "chung", "clip": "clip.mp4"}))
    proj = Project.load(d)
    prep = Prepared(info=probe(clip), normalized=proj.clip_path, words=WORDS, keyframes=[])
    return EditSession(prepared=prep, project=proj, events=Emitter(io.StringIO()))


def text_of(res):
    return "\n".join(c["text"] for c in res["content"] if c["type"] == "text")


async def test_get_transcript_range(session):
    res = await tools.get_transcript(session, {"start": 3.0, "end": 5.0})
    t = text_of(res)
    assert "giá 189K" in t and "chào" not in t and "Clip duration 6." in t


async def test_view_frames_returns_images_and_caps(session):
    res = await tools.view_frames(session, {"times": [0.5, 1, 2, 3, 4, 5, 5.5, 5.9]})
    imgs = [c for c in res["content"] if c["type"] == "image"]
    assert len(imgs) == tools.MAX_FRAMES and imgs[0]["mimeType"] == "image/jpeg"
    base64.b64decode(imgs[0]["data"])


async def test_set_edl_ok_writes_file(session):
    res = await tools.set_edl(session, {"edl": EDL})
    assert not res.get("is_error") and session.edl is not None
    saved = json.loads((session.project.work_dir / "edl.json").read_text())
    assert saved["keep"][0]["start"] == pytest.approx(0.55)


async def test_set_edl_error_counts(session):
    res = await tools.set_edl(session, {"edl": {"keep": [{"start": 0.6, "end": 1.0}]}})
    assert res["is_error"] and "30%" in text_of(res) and session.edl_errors == 1


async def test_preview_requires_edl_and_limit(session):
    assert (await tools.render_preview(session, {}))["is_error"]
    await tools.set_edl(session, {"edl": EDL})
    res = await tools.render_preview(session, {})
    assert not res.get("is_error") and any(c["type"] == "image" for c in res["content"])
    assert '"type": "preview"' in session.events.stream.getvalue()
    session.previews = tools.MAX_PREVIEWS
    assert (await tools.render_preview(session, {}))["is_error"]


async def test_finish(session):
    assert (await tools.finish(session, {"summary": ["x"]}))["is_error"]
    await tools.set_edl(session, {"edl": EDL})
    res = await tools.finish(session, {"summary": ["Bỏ đoạn lặng", "Kết bằng giá"]})
    assert not res.get("is_error") and session.finished and session.summary == ["Bỏ đoạn lặng", "Kết bằng giá"]


def test_build_server(session):
    cfg = tools.build_server(session)
    assert cfg["name"] == "autoedit"
