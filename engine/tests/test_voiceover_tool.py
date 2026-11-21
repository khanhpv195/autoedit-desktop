import io
import json
import subprocess

import pytest

from autoedit import cli
from autoedit.agent import options, tools
from autoedit.agent.prompt import build_edit_prompt
from autoedit.agent.runner import AgentOutcome
from autoedit.agent.session import EditSession
from autoedit.edl import EdlError, VoiceLine, validate_edl
from autoedit.errors import VoiceAuth, VoiceFailed
from autoedit.events import Emitter
from autoedit.prep import Prepared
from autoedit.prep.probe import MediaInfo, probe
from autoedit.project import Project
from autoedit.transcript import Word
from autoedit.voice import eleven

WORDS = [Word("chào", 0.6, 1.0), Word("cả", 1.05, 1.3), Word("nhà", 1.35, 1.8),
         Word("giá", 3.2, 3.6), Word("189K", 3.7, 4.4)]
VO = {"enabled": True, "voice_id": "v1", "voice_name": "Mai"}


def silent_mp3(path, dur=1.0):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono:d={dur}",
                    "-c:a", "libmp3lame", "-b:a", "64k", str(path)], check=True)
    return path


@pytest.fixture
def fake_tts(monkeypatch, tmp_path):
    src = silent_mp3(tmp_path / "one.mp3")
    calls = []

    def tts(text, voice_id, cache_dir):
        calls.append((text, voice_id))
        cache_dir.mkdir(parents=True, exist_ok=True)
        out = cache_dir / f"{eleven.cache_key(voice_id, text)}.mp3"
        out.write_bytes(src.read_bytes())
        return out, [(w, i * 0.2, i * 0.2 + 0.15) for i, w in enumerate(text.split())]
    monkeypatch.setattr(eleven, "tts", tts)
    return calls


def make_project(tmp_path, clip, vo=VO, **over):
    d = tmp_path / "p"
    (d / "input").mkdir(parents=True)
    (d / "input" / "clip.mp4").write_bytes(clip.read_bytes())
    (d / "project.json").write_text(json.dumps({"niche": "chung", "clips": ["clip.mp4"], "voiceover": vo} | over))
    return d


@pytest.fixture
def session(tmp_path, clip):
    proj = Project.load(make_project(tmp_path, clip))
    prep = Prepared(info=probe(clip), normalized=proj.clip_paths[0], words=WORDS, keyframes=[])
    return EditSession(prepared=prep, project=proj, events=Emitter(io.StringIO()))


def text_of(res):
    return "\n".join(c["text"] for c in res["content"] if c["type"] == "text")


async def listed(session):
    cfg = tools.build_server(session)
    handler = cfg["instance"]._request_handlers["tools/list"].handler
    return [t.name for t in (await handler(None, None)).tools]


async def test_tool_registered_only_when_voiceover_on(session):
    assert "voiceover" in await listed(session)
    opts = options.edit_options(session.project.dir, {"type": "sdk"}, "m", voiceover=True)
    assert "mcp__autoedit__voiceover" in opts.allowed_tools
    session.project.voiceover = None
    assert "voiceover" not in await listed(session)
    assert "mcp__autoedit__voiceover" not in options.edit_options(session.project.dir, {"type": "sdk"}, "m").allowed_tools
    assert "voiceover" not in tools.TOOL_NAMES


@pytest.mark.parametrize("lines,match", [
    ([{"at": 0.7, "text": "x" * 121}], "120"),
    ([{"at": 0.7, "text": "a" * 110}] * 6, "600"),
    ([{"at": 99.0, "text": "chào"}], "timeline"),
    ([], "lines"),
])
async def test_limits_return_errors_without_tts(session, fake_tts, lines, match):
    res = await tools.voiceover(session, {"lines": lines})
    assert res["is_error"] and match in text_of(res) and fake_tts == [] and session.voice_calls == 0


async def test_at_must_be_inside_kept_range_once_edl_exists(session, fake_tts):
    await tools.set_edl(session, {"edl": {"keep": [{"start": 0.6, "end": 1.8}, {"start": 3.2, "end": 4.4}]}})
    res = await tools.voiceover(session, {"lines": [{"at": 2.5, "text": "chào"}]})
    assert res["is_error"] and "kept range" in text_of(res) and fake_tts == []


async def test_call_limit(session, fake_tts):
    for _ in range(3):
        assert not (await tools.voiceover(session, {"lines": [{"at": 0.7, "text": "chào cả nhà"}]})).get("is_error")
    res = await tools.voiceover(session, {"lines": [{"at": 0.7, "text": "chào"}]})
    assert res["is_error"] and "3" in text_of(res) and len(fake_tts) == 3


async def test_success_stores_lines_and_reports_windows(session, fake_tts):
    await tools.set_edl(session, {"edl": {"keep": [{"start": 0.6, "end": 1.8}, {"start": 3.2, "end": 4.4}]}})
    res = await tools.voiceover(session, {"lines": [{"at": 0.6, "text": "Áo len xinh"}, {"at": 1.0, "text": "Giá tốt"}]})
    assert not res.get("is_error"), text_of(res)
    out = json.loads(text_of(res))
    assert [line["text"] for line in out["lines"]] == ["Áo len xinh", "Giá tốt"]
    assert out["lines"][0]["duration"] == pytest.approx(1.0, abs=0.08)
    assert out["lines"][0]["out_start"] == pytest.approx(0.05, abs=0.05)
    assert any("overlap" in w for w in out["warnings"])
    assert (0.6, "Áo len xinh") in session.voice_lines and session.voice_calls == 1
    assert fake_tts[0] == ("Áo len xinh", "v1")


async def test_set_edl_validates_voiceover(session, fake_tts):
    keep = [{"start": 0.0, "end": 2.0}, {"start": 3.0, "end": 5.0}]
    await tools.voiceover(session, {"lines": [{"at": 0.2, "text": "một"}, {"at": 3.5, "text": "hai"},
                                              {"at": 0.5, "text": "ba"}, {"at": 4.5, "text": "bốn"}]})
    res = await tools.set_edl(session, {"edl": {"keep": keep, "voiceover": [{"at": 0.2, "text": "một"},
                                                                          {"at": 3.5, "text": "hai"}]}})
    assert not res.get("is_error"), text_of(res)
    assert [c.text for c in session.edl.voiceover] == ["một", "hai"]
    corrected = json.loads(text_of(res))["corrected_edl"]
    assert corrected["voiceover"] == [{"at": 0.2, "text": "một"}, {"at": 3.5, "text": "hai"}]
    bad = [  # unknown line, overlap, past the end
        ([{"at": 0.2, "text": "không có"}], "voiceover"),
        ([{"at": 0.2, "text": "một"}, {"at": 0.5, "text": "ba"}], "overlap"),
        ([{"at": 4.5, "text": "bốn"}], "end"),
    ]
    for cues, match in bad:
        res = await tools.set_edl(session, {"edl": {"keep": keep, "voiceover": cues}})
        assert res["is_error"] and match in text_of(res), text_of(res)


def test_validate_edl_sorts_cues_by_output_time():
    lines = {(5.0, "a"): VoiceLine(5.0, "a", None, 1.0, []), (1.0, "b"): VoiceLine(1.0, "b", None, 1.0, [])}
    edl, _ = validate_edl({"keep": [{"start": 4.0, "end": 7.0}, {"start": 0.0, "end": 3.0}],
                           "voiceover": [{"at": 1.0, "text": "b"}, {"at": 5.0, "text": "a"}]}, [], 8.0,
                          voiceover_on=True, voice_lines=lines)
    assert [c.text for c in edl.voiceover] == ["a", "b"]
    with pytest.raises(EdlError):
        validate_edl({"keep": [{"start": 0.0, "end": 3.0}], "voiceover": [{"at": 1.0, "text": "b"}]}, [], 8.0)


async def test_finish_requires_voiceover_when_on(session, fake_tts):
    await tools.set_edl(session, {"edl": {"keep": [{"start": 0.0, "end": 5.0}]}})
    res = await tools.finish(session, {"summary": ["x"]})
    assert res["is_error"] and "voiceover" in text_of(res)


async def test_fatal_voice_error_aborts_session(session, monkeypatch):
    def boom(*a, **k):
        raise VoiceAuth(eleven.MSG_AUTH)
    monkeypatch.setattr(eleven, "tts", boom)
    res = await tools.voiceover(session, {"lines": [{"at": 0.7, "text": "chào"}]})
    assert res["is_error"] and session.aborted and isinstance(session.fatal, VoiceAuth)


async def test_transient_voice_error_lets_agent_retry(session, monkeypatch):
    def busy(*a, **k):
        raise VoiceFailed("lỗi")
    monkeypatch.setattr(eleven, "tts", busy)
    res = await tools.voiceover(session, {"lines": [{"at": 0.7, "text": "chào"}]})
    assert res["is_error"] and not session.aborted


def test_prompt_voiceover_block(tmp_path):
    proj = Project(dir=tmp_path, niche="chung", clips=["c.mp4"], voiceover=VO, product_info="Áo len 199K")
    prep = Prepared(info=MediaInfo(20, 1080, 1920, 30, False, True), normalized=tmp_path / "n", words=[],
                    keyframes=[])
    p = build_edit_prompt(proj, prep, "", None, None)
    assert "Thông tin sản phẩm (khách nhập): Áo len 199K" in p and "2.5" in p and "0.3" in p and "voiceover" in p
    proj.voiceover = None
    assert "Thông tin sản phẩm" not in build_edit_prompt(proj, prep, "", None, None)
    proj.voiceover, proj.product_info = VO, ""
    assert "Thông tin sản phẩm (khách nhập): (trống)" in build_edit_prompt(proj, prep, "", None, None)


@pytest.fixture
def cli_project(tmp_path, clip, monkeypatch):
    d = make_project(tmp_path, clip)
    import autoedit.prep as prep
    monkeypatch.setattr(prep, "transcribe", lambda v, wd: WORDS)
    return d


def events(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_preflight_quota_blocks_before_agent(cli_project, monkeypatch, capsys):
    monkeypatch.setattr(eleven, "quota", lambda: 599)
    called = []

    async def agent(*a, **k):
        called.append(1)
        return AgentOutcome(False, 0, None)
    monkeypatch.setattr(cli, "run_agent", agent)
    assert cli.main(["edit", "--project", str(cli_project)]) == 1
    assert events(capsys)[-1]["code"] == "VOICE_QUOTA" and called == []
    assert not (cli_project / "runs" / "1").exists()


def test_voice_auth_from_tool_fails_run(cli_project, monkeypatch, capsys):
    monkeypatch.setattr(eleven, "quota", lambda: 5000)

    async def agent(session, prompt, options, **k):
        session.aborted, session.fatal = True, VoiceAuth(eleven.MSG_AUTH)
        return AgentOutcome(False, 1, "aborted")
    monkeypatch.setattr(cli, "run_agent", agent)
    assert cli.main(["edit", "--project", str(cli_project)]) == 1
    last = events(capsys)[-1]
    assert last["code"] == "VOICE_AUTH" and last["message"] == eleven.MSG_AUTH
    assert not (cli_project / "runs" / "1").exists()


def test_agent_failure_with_voiceover_fails_instead_of_fallback(cli_project, monkeypatch, capsys):
    monkeypatch.setattr(eleven, "quota", lambda: 5000)

    async def broken(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(cli, "run_agent", broken)
    assert cli.main(["edit", "--project", str(cli_project)]) == 1
    last = events(capsys)[-1]
    assert last["type"] == "error" and "boom" in last["message"]
    assert not (cli_project / "runs" / "1").exists()


def test_unfinished_agent_with_voiceover_fails(cli_project, monkeypatch, capsys):
    monkeypatch.setattr(eleven, "quota", lambda: 5000)

    async def lazy(*a, **k):
        return AgentOutcome(False, 3, "timeout")
    monkeypatch.setattr(cli, "run_agent", lazy)
    assert cli.main(["edit", "--project", str(cli_project)]) == 1
    last = events(capsys)[-1]
    assert last["code"] == "AGENT_FAILED" and last["message"] == cli.VOICE_AGENT_FAILED


def test_final_render_voice_error_is_not_swallowed(cli_project, monkeypatch, capsys):
    monkeypatch.setattr(eleven, "quota", lambda: 5000)
    lines = {(0.7, "chào"): VoiceLine(0.7, "chào", None, 0.5, [("chào", 0.0, 0.4)])}

    async def agent(session, prompt, options, **k):
        session.edl, _ = validate_edl({"keep": [{"start": 0.0, "end": 5.0}], "voiceover": [{"at": 0.7, "text": "chào"}]},
                                      WORDS, session.prepared.info.duration, voiceover_on=True, voice_lines=lines)
        session.summary, session.finished = ["x"], True
        return AgentOutcome(True, 3, None)
    monkeypatch.setattr(cli, "run_agent", agent)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)     # cache is empty: re-synthesis needs the key
    assert cli.main(["edit", "--project", str(cli_project)]) == 1
    assert events(capsys)[-1]["code"] == "VOICE_AUTH"
    assert not (cli_project / "runs" / "1").exists()


def test_voiceover_skips_transcript_fix_notes():
    lines = {(0.7, "áo len"): VoiceLine(0.7, "áo len", None, 0.5, [])}
    _, notes = validate_edl({"keep": [{"start": 0.0, "end": 5.0}], "voiceover": [{"at": 0.7, "text": "áo len"}],
                             "emphasis": [{"at": 0.9, "word": "len"}]}, WORDS, 6.0, voiceover_on=True,
                            voice_lines=lines)
    assert not any("emphasis" in n for n in notes)
