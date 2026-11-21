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
    (d / "project.json").write_text(json.dumps({"niche": "chung", "clips": ["clip.mp4"]}))
    proj = Project.load(d)
    prep = Prepared(info=probe(clip), normalized=proj.clip_paths[0], words=WORDS, keyframes=[])
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
    assert saved["keep"][0]["start"] == pytest.approx(0.55, abs=0.02)


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


async def test_build_server(session):
    cfg = tools.build_server(session)
    assert cfg["name"] == "autoedit"
    handler = cfg["instance"]._request_handlers["tools/list"].handler
    listed = (await handler(None, None)).tools
    assert [t.name for t in listed] == list(tools.TOOL_NAMES) and len(listed) == 5
    assert "keep" in next(t for t in listed if t.name == "set_edl").input_schema["properties"]["edl"]["properties"]


async def test_set_edl_accepts_json_string(session):
    res = await tools.set_edl(session, {"edl": json.dumps(EDL)})
    assert not res.get("is_error") and session.edl is not None
    res = await tools.set_edl(session, {"edl": "{not json"})
    assert res["is_error"] and "JSON" in text_of(res)


async def test_set_edl_schema_describes_edl_fields():
    edl = tools.SCHEMAS["set_edl"][1]["properties"]["edl"]
    assert {"keep", "hook", "caption_fixes", "emphasis", "cta_text", "music"} <= set(edl["properties"])
    assert edl["required"] == ["keep"] and edl["properties"]["keep"]["items"]["required"] == ["start", "end"]


async def test_three_invalid_edls_abort_the_session(session):
    bad = {"edl": {"keep": [{"start": 0.6, "end": 1.0}]}}
    for _ in range(3):
        await tools.set_edl(session, bad)
    assert session.aborted
    res = await tools.set_edl(session, bad)
    assert res["is_error"]


async def test_ffmpeg_work_runs_off_the_event_loop(session, monkeypatch):
    import threading
    seen = []
    real_render, real_frame = tools.render, tools.frame_at
    monkeypatch.setattr(tools, "render", lambda *a, **k: seen.append(threading.current_thread()) or real_render(*a, **k))
    monkeypatch.setattr(tools, "frame_at", lambda *a, **k: seen.append(threading.current_thread()) or real_frame(*a, **k))
    await tools.set_edl(session, {"edl": EDL})
    await tools.render_preview(session, {})
    await tools.view_frames(session, {"times": [1.0]})
    assert seen and all(t is not threading.main_thread() for t in seen)


async def test_view_frames_session_cap(session):
    for _ in range(tools.MAX_VIEWED_FRAMES // tools.MAX_FRAMES):
        res = await tools.view_frames(session, {"times": [0.5, 1, 2, 3, 4, 5]})
        assert not res.get("is_error")
    res = await tools.view_frames(session, {"times": [1.0]})
    assert res.get("is_error") and "limit" in text_of(res)
    assert session.frames_viewed == tools.MAX_VIEWED_FRAMES


async def test_preview_text_lists_qc_issues(session, monkeypatch):
    from autoedit.render.pipeline import RenderResult
    await tools.set_edl(session, {"edl": EDL})
    real = tools.render

    def fake_render(*a, **k):
        res = real(*a, **k)
        return RenderResult(res.path, res.duration, None, False, ["khung đứng 3.20–4.10s", "tiếng bụp ở cắt 1.20s"])
    monkeypatch.setattr(tools, "render", fake_render)
    t = text_of(await tools.render_preview(session, {}))
    assert "Kiểm tra: khung đứng 3.20–4.10s; tiếng bụp ở cắt 1.20s" in t
