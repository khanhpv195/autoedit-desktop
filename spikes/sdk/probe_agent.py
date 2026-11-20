import asyncio, json, os, sys
from pathlib import Path
from claude_agent_sdk import (ClaudeAgentOptions, AssistantMessage, ResultMessage, RateLimitEvent,
                              SystemMessage, TextBlock, ToolUseBlock, create_sdk_mcp_server, query, tool)

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
calls = []

@tool("add", "Add two integers", {"a": int, "b": int})
async def add(args):
    calls.append(args)
    return {"content": [{"type": "text", "text": str(args["a"] + args["b"])}]}

async def main():
    server = create_sdk_mcp_server(name="spike", tools=[add])
    opts = ClaudeAgentOptions(
        cwd=str(BASE / "agent"),
        tools=["Skill"],
        skills=["hello"],
        setting_sources=["project"],
        mcp_servers={"spike": server},
        allowed_tools=["mcp__spike__add"],
        max_turns=6,
        model=os.environ.get("SPIKE_MODEL", "claude-opus-5-5"),
        cli_path=os.environ.get("SPIKE_CLI") or None,   # Step 6: CLI outside the package
        env={} if os.environ.get("SPIKE_AUTOUPDATE") else {"DISABLE_AUTOUPDATER": "1"},
        strict_mcp_config=bool(os.environ.get("SPIKE_STRICT")),
    )
    prompt = ("1) Use the add tool to compute 2+40. 2) Greet me in the house style. "
              "3) Try to run the shell command `ls` and tell me whether you could.")
    async for m in query(prompt=prompt, options=opts):
        if isinstance(m, SystemMessage) and m.subtype == "init":
            print("INIT tools:", m.data.get("tools"), "skills:", m.data.get("skills"), file=sys.stderr)
        elif isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, ToolUseBlock):
                    print("TOOL_USE", b.name, json.dumps(b.input), file=sys.stderr)
                elif isinstance(b, TextBlock):
                    print("TEXT", b.text[:300], file=sys.stderr)
            if m.error:
                print("ASSISTANT_ERROR", m.error, file=sys.stderr)
        elif isinstance(m, RateLimitEvent):
            print("RATE_LIMIT", m.rate_limit_info, file=sys.stderr)
        elif isinstance(m, ResultMessage):
            print("RESULT", m.subtype, m.num_turns, m.is_error, (m.result or ""), file=sys.stderr)
    print("CALLS", calls, file=sys.stderr)

asyncio.run(main())
