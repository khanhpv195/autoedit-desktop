import os
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions

from autoedit.agent.tools import TOOL_NAMES
from autoedit.claude_cli import find_cli

DEFAULT_MODEL = "claude-sonnet-5-5"
BASE_ENV = {"DISABLE_AUTOUPDATER": "1"}   # our pinned CLI must never update itself
MAX_BUFFER = 32 * 1024 * 1024    # SDK default 1 MB overflows on a tool result with 6 base64 frames
EDIT_TOOLS = [f"mcp__autoedit__{n}" for n in TOOL_NAMES]


def model() -> str:
    return os.environ.get("AUTOEDIT_CLAUDE_MODEL", DEFAULT_MODEL)


def edit_options(agent_dir: Path, server, model: str, stderr=None, user_mcp: dict | None = None,
                 user_mcp_file: Path | None = None, voiceover: bool = False) -> ClaudeAgentOptions:
    """`user_mcp` only supplies the server names to allow. Their configs (secrets) travel in `user_mcp_file`
    (see mcp_user.config_file) as a second --mcp-config, never inside `mcp_servers`: the SDK would put those
    on the CLI command line."""
    user_mcp = {n: c for n, c in (user_mcp or {}).items() if n != "autoedit"}
    return ClaudeAgentOptions(
        cwd=str(agent_dir),
        tools=[],                        # no built-in tools at all: only our MCP tools (skills ride in the first message)
        setting_sources=["project"],     # agent/CLAUDE.md only, never ~/.claude
        mcp_servers={"autoedit": server},
        extra_args={"mcp-config": str(user_mcp_file)} if user_mcp and user_mcp_file else {},
        allowed_tools=EDIT_TOOLS + (["mcp__autoedit__voiceover"] if voiceover else [])
        + [f"mcp__{n}" for n in user_mcp],
        max_turns=20,
        model=model,
        cli_path=find_cli(),             # None only when running from source: SDK uses its own copy
        env=dict(BASE_ENV),
        max_buffer_size=MAX_BUFFER,
        stderr=stderr,                   # CLI subprocess stderr lines (never its env), e.g. into run.log
        strict_mcp_config=True,          # spike: without it the account's claude.ai connectors leak in
    )


def plain_options(agent_dir: Path, model: str, max_turns: int, output_format: dict | None = None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(cwd=str(agent_dir), tools=[], setting_sources=[], max_turns=max_turns,
                              model=model, output_format=output_format, cli_path=find_cli(), env=dict(BASE_ENV),
                              strict_mcp_config=True)
