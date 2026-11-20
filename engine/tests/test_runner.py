import io, time
import pytest
from claude_agent_sdk import AssistantMessage, RateLimitEvent, RateLimitInfo, ResultMessage, TextBlock, ToolUseBlock
from autoedit.agent.options import edit_options, EDIT_TOOLS, SKILLS
from autoedit.agent.runner import run_agent
from claude_agent_sdk import ProcessError, ResultError, CLINotFoundError
from autoedit.errors import RateLimited, NoAuth, SetupRequired
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
    async def q(prompt, options):
        yield AssistantMessage(content=[TextBlock("Mình đọc lời thoại trước"),
                                        ToolUseBlock("1", "mcp__autoedit__get_transcript", {})], model="m")
        yield result(5)
        s.finished, s.edl = True, object()
        yield result(5)
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
    assert o.strict_mcp_config is True and o.max_buffer_size >= 16 * 1024 * 1024


def test_plain_options_also_pin_cli(tmp_path, monkeypatch):
    import autoedit.agent.options as opt
    monkeypatch.setattr(opt, "find_cli", lambda: None)
    o = opt.plain_options(tmp_path, "m", 1)
    assert o.tools == [] and o.setting_sources == [] and o.cli_path is None
    assert o.env["DISABLE_AUTOUPDATER"] == "1" and o.strict_mcp_config is True


def test_clip_cuts_on_word_boundary():
    from autoedit.agent.runner import _clip
    assert _clip("ngắn") == "ngắn"
    text = ("abcd " * 100).strip()
    out = _clip(text)
    assert out.endswith("…") and len(out) <= 281
    assert out[:-1].split()[-1] == "abcd"


def finish_then(*after, err=None):
    """Fake CLI: finish tool runs (session.finished), then the stream ends with errors."""
    s = S()
    async def q(prompt, options):
        yield AssistantMessage(content=[ToolUseBlock("1", "mcp__autoedit__finish", {})], model="m")
        s.finished, s.edl = True, object()
        for m in after:
            yield m
        if err:
            raise err
    return s, q


async def test_result_error_after_finish_is_success():
    r = ResultMessage(subtype="error_max_turns", duration_ms=1, duration_api_ms=1, is_error=True, num_turns=15,
                      session_id="s")
    s, q = finish_then(r, err=ResultError("x", {"subtype": "error_max_turns"}))
    out = await run_agent(s, "p", None, query_fn=q)
    assert out.finished and out.turns == 15


async def test_stops_consuming_stream_after_finish():
    consumed = []
    s = S()
    async def q(prompt, options):
        yield AssistantMessage(content=[ToolUseBlock("1", "mcp__autoedit__finish", {})], model="m")
        s.finished, s.edl = True, object()
        consumed.append("a")
        yield result(3)
        consumed.append("b")
        raise ProcessError("never reached")
    out = await run_agent(s, "p", None, query_fn=q)
    assert out.finished and consumed == ["a"]


async def test_crash_after_finish_is_success():
    s, q = finish_then(err=ProcessError("boom", exit_code=1))
    assert (await run_agent(s, "p", None, query_fn=q)).finished


NOT_LOGGED = {"subtype": "success", "result": "Not logged in · Please run /login", "is_error": True}


@pytest.mark.parametrize("exc,expected", [
    (ResultError("e", {"result": "Not logged in · Please run /login"}), NoAuth),
    (ResultError("e", {"api_error_status": 401, "result": "x"}), NoAuth),
    (ProcessError("fail", exit_code=1, stderr="Invalid API key · Please run /login"), NoAuth),
    (ResultError("e", {"api_error_status": 429, "result": "API Error"}), RateLimited),
    (ResultError("e", {"result": "5-hour usage limit reached"}), RateLimited),
    (ProcessError("x", stderr="rate limit exceeded"), RateLimited),
    (CLINotFoundError("nope"), SetupRequired),
])
async def test_sdk_exceptions_are_classified(exc, expected):
    async def q(prompt, options):
        yield result()
        raise exc
    with pytest.raises(expected):
        await run_agent(S(), "p", None, query_fn=q)


async def test_error_result_message_without_raise_is_classified():
    r = ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=True, num_turns=1,
                      session_id="s", result="Not logged in · Please run /login")
    with pytest.raises(NoAuth):
        await run_agent(S(), "p", None, query_fn=fake(r))
    r2 = ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=True, num_turns=1,
                       session_id="s", result="API Error", api_error_status=429)
    with pytest.raises(RateLimited):
        await run_agent(S(), "p", None, query_fn=fake(r2))


async def test_unclassified_error_before_finish_still_raises():
    async def q(prompt, options):
        yield result()
        raise ProcessError("weird", exit_code=1)
    with pytest.raises(ProcessError):
        await run_agent(S(), "p", None, query_fn=q)


async def test_aborted_session_ends_run_and_closes_stream():
    s = S(); s.aborted = False
    closed = []
    async def q(prompt, options):
        try:
            yield AssistantMessage(content=[TextBlock("x")], model="m")
            s.aborted = True
            yield AssistantMessage(content=[TextBlock("y")], model="m")
            yield AssistantMessage(content=[TextBlock("z")], model="m")
        finally:
            closed.append(1)
    out = await run_agent(s, "p", None, query_fn=q)
    assert not out.finished and out.error == "aborted" and closed
