import io, time
import pytest
from claude_agent_sdk import AssistantMessage, RateLimitEvent, RateLimitInfo, ResultMessage, TextBlock, ToolUseBlock
from autoedit.agent.options import edit_options, EDIT_TOOLS, SKILLS
from autoedit.agent.runner import run_agent
from autoedit.errors import RateLimited, NoAuth
from autoedit.events import Emitter


class S:  # minimal stand-in for EditSession
    def __init__(self):
        self.events = Emitter(io.StringIO()); self.finished = False; self.edl = None


def result(turns=4, is_error=False):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=is_error,
                         num_turns=turns, session_id="s")


def fake(*msgs, on_start=None):
    async def q(prompt, options):
        if on_start:
            on_start()
        for m in msgs:
            yield m
    return q


async def test_emits_tool_labels_and_finishes():
    s = S()
    def mark():
        s.finished, s.edl = True, object()
    q = fake(AssistantMessage(content=[TextBlock("Mình đọc lời thoại trước"),
                                       ToolUseBlock("1", "mcp__autoedit__get_transcript", {})], model="m"),
             result(5), on_start=mark)
    out = await run_agent(s, "p", None, query_fn=q)
    assert out.finished and out.turns == 5
    log = s.events.stream.getvalue()
    assert "Đọc lời thoại" in log and '"tool": "get_transcript"' in log and "Mình đọc" in log


async def test_not_finished_when_agent_never_calls_finish():
    out = await run_agent(S(), "p", None, query_fn=fake(result()))
    assert not out.finished


async def test_rate_limit_event_raises_with_retry_time():
    reset = int(time.time()) + 3600
    q = fake(RateLimitEvent(rate_limit_info=RateLimitInfo(status="rejected", resets_at=reset), uuid="u", session_id="s"))
    with pytest.raises(RateLimited) as e:
        await run_agent(S(), "p", None, query_fn=q)
    assert e.value.retry_at and "T" in e.value.retry_at


async def test_assistant_rate_limit_error_raises():
    with pytest.raises(RateLimited):
        await run_agent(S(), "p", None, query_fn=fake(AssistantMessage(content=[], model="m", error="rate_limit")))


async def test_auth_error_raises():
    with pytest.raises(NoAuth):
        await run_agent(S(), "p", None,
                        query_fn=fake(AssistantMessage(content=[], model="m", error="authentication_failed")))


async def test_timeout_returns_outcome():
    import asyncio
    async def slow(prompt, options):
        await asyncio.sleep(5)
        yield result()
    out = await run_agent(S(), "p", None, query_fn=slow, timeout=0.05)
    assert out.error == "timeout" and not out.finished


def test_edit_options_lock_down_tools(tmp_path, monkeypatch):
    import autoedit.agent.options as opt
    monkeypatch.setattr(opt, "find_cli", lambda: tmp_path / "claude")
    o = edit_options(tmp_path, {"type": "sdk", "name": "autoedit"}, "claude-opus-5-5")
    assert o.tools == ["Skill"] and o.skills == SKILLS and o.setting_sources == ["project"]
    assert o.allowed_tools == EDIT_TOOLS and o.max_turns == 15 and o.cwd == str(tmp_path)
    assert o.cli_path == tmp_path / "claude" and o.env == {"DISABLE_AUTOUPDATER": "1"}
    assert o.strict_mcp_config is True


def test_plain_options_also_pin_cli(tmp_path, monkeypatch):
    import autoedit.agent.options as opt
    monkeypatch.setattr(opt, "find_cli", lambda: None)
    o = opt.plain_options(tmp_path, "m", 1)
    assert o.tools == [] and o.setting_sources == [] and o.cli_path is None
    assert o.env["DISABLE_AUTOUPDATER"] == "1" and o.strict_mcp_config is True
