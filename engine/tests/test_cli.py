import json
import pytest
from autoedit import cli
from autoedit.agent.runner import AgentOutcome
from autoedit.edl import validate_edl
from autoedit.errors import RateLimited
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
    assert "0.1.0" in capsys.readouterr().out


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
