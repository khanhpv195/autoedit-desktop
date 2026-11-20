import os
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions

from autoedit.agent.tools import TOOL_NAMES
from autoedit.claude_cli import find_cli

DEFAULT_MODEL = "claude-opus-5-5"
BASE_ENV = {"DISABLE_AUTOUPDATER": "1"}   # our pinned CLI must never update itself
SKILLS = ["video-use", "edit-video", "niche-hooks"]
EDIT_TOOLS = [f"mcp__autoedit__{n}" for n in TOOL_NAMES]


def model() -> str:
    return os.environ.get("AUTOEDIT_CLAUDE_MODEL", DEFAULT_MODEL)


def edit_options(agent_dir: Path, server, model: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=str(agent_dir),
        tools=["Skill"],                 # no Bash/Read/Write/Edit: only Skill + our MCP tools
        skills=SKILLS,
        setting_sources=["project"],     # agent/CLAUDE.md + agent/.claude/skills only, never ~/.claude
        mcp_servers={"autoedit": server},
        allowed_tools=EDIT_TOOLS,
        max_turns=15,
        model=model,
        cli_path=find_cli(),             # None only when running from source: SDK uses its own copy
        env=dict(BASE_ENV),
        strict_mcp_config=True,          # spike: without it the account's claude.ai connectors leak in
    )


def plain_options(agent_dir: Path, model: str, max_turns: int, output_format: dict | None = None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(cwd=str(agent_dir), tools=[], setting_sources=[], max_turns=max_turns,
                              model=model, output_format=output_format, cli_path=find_cli(), env=dict(BASE_ENV),
                              strict_mcp_config=True)
