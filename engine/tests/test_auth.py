import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
from autoedit.agent.auth import detect_auth, auth_check
from autoedit.errors import NoAuth


def test_detect_order(tmp_path):
    assert detect_auth({"CLAUDE_CODE_OAUTH_TOKEN": "x"}, tmp_path, lambda: False) == "subscription-token"
    assert detect_auth({"ANTHROPIC_API_KEY": "x"}, tmp_path, lambda: False) == "api-key"
    (tmp_path / ".claude").mkdir(); (tmp_path / ".claude" / ".credentials.json").write_text("{}")
    assert detect_auth({}, tmp_path, lambda: False) == "claude-code"


def test_detect_keychain_and_none(tmp_path):
    assert detect_auth({}, tmp_path, lambda: True) == "claude-code"
    assert detect_auth({}, tmp_path, lambda: False) is None


async def test_auth_check_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "x")
    async def q(prompt, options):
        yield AssistantMessage(content=[TextBlock("OK")], model="m")
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s")
    assert await auth_check(tmp_path, query_fn=q) == "subscription-token"


async def test_auth_check_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "x")
    async def q(prompt, options):
        yield AssistantMessage(content=[], model="m", error="authentication_failed")
    with pytest.raises(NoAuth):
        await auth_check(tmp_path, query_fn=q)


async def test_auth_check_nothing_configured(tmp_path, monkeypatch):
    import autoedit.agent.auth as a
    monkeypatch.setattr(a, "detect_auth", lambda *x, **k: None)
    with pytest.raises(NoAuth):
        await auth_check(tmp_path)


async def test_auth_check_rate_limited_is_not_no_auth(tmp_path, monkeypatch):
    from claude_agent_sdk import ResultError
    from autoedit.errors import RateLimited
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "x")
    async def q(prompt, options):
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=True, num_turns=1,
                            session_id="s", result="usage limit reached", api_error_status=429)
    with pytest.raises(RateLimited):
        await auth_check(tmp_path, query_fn=q)
    async def q2(prompt, options):
        yield AssistantMessage(content=[], model="m")
        raise ResultError("e", {"result": "Not logged in · Please run /login"})
    with pytest.raises(NoAuth):
        await auth_check(tmp_path, query_fn=q2)
