import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ResultMessage, query

from autoedit.agent.options import model, plain_options
from autoedit.claude_cli import find_cli
from autoedit.errors import NoAuth


def _mac_keychain_has_claude() -> bool:
    if sys.platform != "darwin":
        return False
    r = subprocess.run(["security", "find-generic-password", "-s", "Claude Code-credentials"],
                       capture_output=True, timeout=5)
    return r.returncode == 0


def detect_auth(env: Mapping[str, str] | None = None, home: Path | None = None, keychain=None) -> str | None:
    env = os.environ if env is None else env
    if env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return "subscription-token"
    if env.get("ANTHROPIC_API_KEY"):
        return "api-key"
    cfg = Path(env["CLAUDE_CONFIG_DIR"]) if env.get("CLAUDE_CONFIG_DIR") else (home or Path.home()) / ".claude"
    if (cfg / ".credentials.json").exists():
        return "claude-code"
    if (keychain or _mac_keychain_has_claude)():
        return "claude-code"
    return None


async def auth_check(agent_dir: Path, *, query_fn=query) -> str:
    find_cli()  # SETUP_REQUIRED before anything else when the frozen app has no CLI yet
    source = detect_auth()
    if source is None:
        raise NoAuth("Chưa đăng nhập Claude")
    async for msg in query_fn(prompt="Reply with exactly: OK", options=plain_options(agent_dir, model(), 1)):
        if isinstance(msg, AssistantMessage) and msg.error in ("authentication_failed", "billing_error"):
            raise NoAuth("Tài khoản Claude không dùng được")
        if isinstance(msg, ResultMessage) and msg.is_error:
            raise NoAuth(f"Không gọi được Claude: {msg.result or msg.subtype}")
    return source
