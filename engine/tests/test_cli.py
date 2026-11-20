import json
import pytest
import autoedit
from autoedit import cli
from autoedit.agent.runner import AgentOutcome
from autoedit.edl import validate_edl
from autoedit.errors import NoAuth, RateLimited
from autoedit.fallback import FALLBACK_SUMMARY
from autoedit.transcript import Word

WORDS = [Word("chào", 0.6, 1.0), Word("cả", 1.05, 1.3), Word("nhà", 1.35, 1.8),
         Word("giá", 3.2, 3.6), Word("189K", 3.7, 4.4)]


@pytest.fixture
def project(tmp_path, clip, monkeypatch):
    d = tmp_path / "p"; (d / "input").mkdir(parents=True)
    (d / "input" / "clip.mp4").write_bytes(clip.read_bytes())
    (d / "project.json").write_text(json.dumps({"niche": "my-pham", "clip": "clip.mp4"}))
    import autoedit.prep as prep
    monkeypatch.setattr(prep, "transcribe", lambda v, wd: WORDS)
    return d


def events(capsys):
    return [json.loads(l) for l in capsys.readouterr().out.splitlines()]


def test_version(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == autoedit.__version__


def test_edit_happy_path(project, monkeypatch, capsys):
    async def fake_agent(session, prompt, options, **kw):
        session.edl, _ = validate_edl({"keep": [{"start": 0.6, "end": 1.8}, {"start": 3.2, "end": 4.4}]},
                                      WORDS, session.prepared.info.duration)
        session.summary, session.finished = ["Bỏ đoạn lặng"], True
        session.events.agent("Chọn đoạn cắt", tool="set_edl")
        return AgentOutcome(True, 6, None)
    monkeypatch.setattr(cli, "run_agent", fake_agent)
    assert cli.main(["edit", "--project", str(project), "--prompt", "gọn gàng"]) == 0
    ev = events(capsys)
    done = ev[-1]
    assert done["type"] == "done" and done["summary"] == ["Bỏ đoạn lặng"] and done["usage"]["turns"] == 6
    assert (project / "runs" / "1" / "final.mp4").exists() and (project / "runs" / "1" / "edl.json").exists()
    assert "set_edl" in (project / "runs" / "1" / "agent.jsonl").read_text()
    pj = json.loads((project / "project.json").read_text())
    assert pj["runs"][0]["n"] == 1 and pj["prompt"] == "gọn gàng"


def test_edit_save_keeps_posts_published_during_the_run(project, monkeypatch, capsys):
    from autoedit.project import update_project

    async def fake_agent(session, prompt, options, **kw):
        update_project(project, lambda d: d.setdefault("posts", []).append({"id": "p9", "run": 0}))   # a publish lands
        return AgentOutcome(False, 1, "x")
    monkeypatch.setattr(cli, "run_agent", fake_agent)
    assert cli.main(["edit", "--project", str(project)]) == 0
    pj = json.loads((project / "project.json").read_text())
    assert pj["posts"] == [{"id": "p9", "run": 0}] and pj["runs"][0]["n"] == 1


def test_edit_falls_back_when_agent_fails(project, monkeypatch, capsys):
    async def broken(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(cli, "run_agent", broken)
    assert cli.main(["edit", "--project", str(project)]) == 0
    done = events(capsys)[-1]
    assert done["summary"] == [FALLBACK_SUMMARY] and done["usage"]["fallback"] is True


def test_edit_rate_limit_no_fallback(project, monkeypatch, capsys):
    async def limited(*a, **k):
        raise RateLimited("hết lượt", "2026-11-20T14:30:00+07:00")
    monkeypatch.setattr(cli, "run_agent", limited)
    assert cli.main(["edit", "--project", str(project)]) == 2
    last = events(capsys)[-1]
    assert last == {"type": "error", "code": "RATE_LIMIT", "message": "hết lượt", "retry_at": "2026-11-20T14:30:00+07:00"}
    assert not (project / "runs" / "1").exists()


def test_edit_no_auth_no_fallback(project, monkeypatch, capsys):
    async def nologin(*a, **k):
        raise NoAuth("Chưa đăng nhập")
    monkeypatch.setattr(cli, "run_agent", nologin)
    assert cli.main(["edit", "--project", str(project)]) == 1
    assert events(capsys)[-1]["code"] == "NO_AUTH"
    assert not (project / "runs" / "1").exists()


def test_bad_project(tmp_path, capsys):
    assert cli.main(["edit", "--project", str(tmp_path / "nope")]) == 1
    assert events(capsys)[-1]["code"] == "BAD_INPUT"


def test_analyze(project, monkeypatch, capsys):
    async def fake(prepared, niche, agent_dir, exclude=None, **kw):
        return [{"title": "t", "hook": "h", "outline": ["a"], "prompt": "p"}] * 3
    monkeypatch.setattr(cli, "run_analyze", fake)
    assert cli.main(["analyze", "--project", str(project)]) == 0
    assert events(capsys)[-1]["type"] == "cards"


def test_setup(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "install_cli", lambda events: tmp_path / "claude")
    assert cli.main(["setup"]) == 0
    assert events(capsys)[-1] == {"type": "setup", "claude_cli": str(tmp_path / "claude")}


def test_setup_required_error(monkeypatch, capsys):
    from autoedit.errors import SetupRequired
    async def missing(agent_dir, **kw):
        raise SetupRequired("Chưa tải Claude")
    monkeypatch.setattr(cli, "auth_check", missing)
    assert cli.main(["auth-check"]) == 1
    assert events(capsys)[-1]["code"] == "SETUP_REQUIRED"


def test_auth_check(monkeypatch, capsys):
    async def ok(agent_dir, **kw):
        return "claude-code"
    monkeypatch.setattr(cli, "auth_check", ok)
    assert cli.main(["auth-check"]) == 0
    assert events(capsys)[-1] == {"type": "auth", "source": "claude-code"}


def test_edit_logs_sdk_messages_and_stderr(project, monkeypatch, capsys):
    import sys
    from claude_agent_sdk import AssistantMessage, TextBlock, ToolResultBlock, UserMessage
    async def fake_agent(session, prompt, options, on_message=None, **kw):
        on_message(AssistantMessage(content=[TextBlock("xin chào")], model="m"))
        on_message(UserMessage(content=[ToolResultBlock("1", [{"type": "image", "data": "B" * 999}])]))
        print("some stderr line", file=sys.stderr)
        session.edl, _ = validate_edl({"keep": [{"start": 0.6, "end": 1.8}, {"start": 3.2, "end": 4.4}]},
                                      WORDS, session.prepared.info.duration)
        session.summary, session.finished = ["ok"], True
        return AgentOutcome(True, 3, None)
    monkeypatch.setattr(cli, "run_agent", fake_agent)
    assert cli.main(["edit", "--project", str(project)]) == 0
    log = (project / "runs" / "1" / "agent.jsonl").read_text(encoding="utf-8")
    assert "xin chào" in log and "B" * 50 not in log and "image omitted" in log and '"type": "step"' in log
    assert "some stderr line" in (project / "runs" / "1" / "run.log").read_text(encoding="utf-8")


def test_render_failure_of_agent_edl_retries_with_fallback(project, monkeypatch, capsys):
    from autoedit.errors import RenderFailed
    real_render = cli.render
    async def fake_agent(session, prompt, options, **kw):
        session.edl, _ = validate_edl({"keep": [{"start": 0.6, "end": 1.8}, {"start": 3.2, "end": 4.4}]},
                                      WORDS, session.prepared.info.duration)
        session.summary, session.finished = ["agent edit"], True
        return AgentOutcome(True, 3, None)
    calls = []
    def flaky(prepared, proj, edl, out, preview):
        calls.append(edl)
        if len(calls) == 1:
            raise RenderFailed("boom")
        return real_render(prepared, proj, edl, out, preview)
    monkeypatch.setattr(cli, "run_agent", fake_agent)
    monkeypatch.setattr(cli, "render", flaky)
    assert cli.main(["edit", "--project", str(project)]) == 0
    done = events(capsys)[-1]
    assert done["type"] == "done" and done["summary"] == [FALLBACK_SUMMARY] and done["usage"]["fallback"] is True
    assert len(calls) == 2


def test_failed_render_removes_run_dir(project, monkeypatch, capsys):
    from autoedit.errors import RenderFailed
    async def fake_agent(session, prompt, options, **kw):
        return AgentOutcome(False, 1, "aborted")
    def broken(*a, **k):
        raise RenderFailed("boom")
    monkeypatch.setattr(cli, "run_agent", fake_agent)
    monkeypatch.setattr(cli, "render", broken)
    assert cli.main(["edit", "--project", str(project)]) == 1
    assert events(capsys)[-1]["code"] == "RENDER_FAILED"
    assert not (project / "runs" / "1").exists()


def test_cli_subprocess_stderr_goes_to_run_log(project, monkeypatch, capsys):
    async def agent(session, prompt, options, **kw):
        options.stderr("cli says hello")
        return AgentOutcome(False, 0, "x")
    monkeypatch.setattr(cli, "run_agent", agent)
    assert cli.main(["edit", "--project", str(project)]) == 0
    assert "[claude] cli says hello" in (project / "runs" / "1" / "run.log").read_text()


def test_broken_pipe_on_done_keeps_the_saved_run(project, monkeypatch, capsys):
    from autoedit.events import Emitter
    async def fake_agent(session, prompt, options, **kw):
        return AgentOutcome(False, 1, "aborted")
    def gone(self, *a, **k):
        raise BrokenPipeError("app quit")
    monkeypatch.setattr(cli, "run_agent", fake_agent)
    monkeypatch.setattr(Emitter, "done", gone)
    assert cli.main(["edit", "--project", str(project)]) == 0
    assert (project / "runs" / "1" / "final.mp4").exists()
    pj = json.loads((project / "project.json").read_text())
    assert pj["runs"][0]["n"] == 1

