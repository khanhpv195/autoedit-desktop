import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from autoedit import cli, mcp_user
from autoedit.agent.options import EDIT_TOOLS, edit_options
from autoedit.agent.prompt import build_edit_prompt
from autoedit.errors import AgentFailed

ECHO = str(Path(__file__).parent / "fixtures" / "echo_mcp.py")


def test_load_filters_and_converts(capsys):
    env = {"AUTOEDIT_MCP": json.dumps({
        "shop-info": {"type": "stdio", "command": "uvx", "args": ["x", 1], "env": {"TOKEN": "sekret-value"}},
        "web": {"type": "http", "url": "https://m.example/mcp", "headers": {"Authorization": "Bearer abc"}},
        "autoedit": {"type": "stdio", "command": "evil"},
        "Bad Name": {"type": "stdio", "command": "x"},
        "no-cmd": {"type": "stdio"},
        "weird": {"type": "ftp", "url": "x"}})}
    out = mcp_user.load(env)
    assert out == {
        "shop-info": {"type": "stdio", "command": "uvx", "args": ["x", "1"], "env": {"TOKEN": "sekret-value"}},
        "web": {"type": "http", "url": "https://m.example/mcp", "headers": {"Authorization": "Bearer abc"}}}
    err = capsys.readouterr().err
    assert "sekret-value" not in err and "Bearer" not in err


def test_load_defaults_and_broken_json(capsys):
    assert mcp_user.load({}) == {}
    assert mcp_user.load({"AUTOEDIT_MCP": "{not json sekret"}) == {}
    assert mcp_user.load({"AUTOEDIT_MCP": "[1]"}) == {}
    assert "sekret" not in capsys.readouterr().err


def test_load_caps_at_ten():
    env = {"AUTOEDIT_MCP": json.dumps({f"s{i}": {"type": "http", "url": "http://x"} for i in range(15)})}
    assert len(mcp_user.load(env)) == 10


def test_edit_options_with_user_mcp(tmp_path, monkeypatch):
    monkeypatch.setattr("autoedit.agent.options.find_cli", lambda: None)
    user = {"shop": {"type": "http", "url": "http://x", "headers": {"Authorization": "Bearer SECRET"}}}
    o = edit_options(tmp_path, {"type": "sdk", "name": "autoedit"}, "m", None, user, tmp_path / "u.json")
    # customer configs never enter mcp_servers (the SDK would serialise them onto the command line)
    assert set(o.mcp_servers) == {"autoedit"} and "SECRET" not in repr(o.mcp_servers) + repr(o.extra_args)
    assert o.extra_args == {"mcp-config": str(tmp_path / "u.json")}
    assert o.allowed_tools == EDIT_TOOLS + ["mcp__shop"] and o.strict_mcp_config is True
    o2 = edit_options(tmp_path, {"type": "sdk", "name": "autoedit"}, "m", None, {"autoedit": {"type": "http", "url": "x"}})
    assert o2.mcp_servers == {"autoedit": {"type": "sdk", "name": "autoedit"}} and o2.allowed_tools == EDIT_TOOLS
    assert o2.extra_args == {}


def test_config_file_is_private_and_removed(tmp_path):
    import json, os, stat
    servers = {"shop": {"type": "stdio", "command": "npx", "args": [], "env": {"TOKEN": "SECRET"}}}
    with mcp_user.config_file(servers) as path:
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        assert json.loads(path.read_text()) == {"mcpServers": servers}
    assert not path.exists()
    with pytest.raises(RuntimeError):
        with mcp_user.config_file(servers) as path:
            raise RuntimeError
    assert not path.exists()
    with mcp_user.config_file({}) as none:
        assert none is None


def test_sdk_command_line_has_no_customer_secret(tmp_path, monkeypatch):
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
    monkeypatch.setattr("autoedit.agent.options.find_cli", lambda: tmp_path / "claude")
    user = {"shop": {"type": "stdio", "command": "npx", "args": [], "env": {"TOKEN": "SECRET"}}}
    with mcp_user.config_file(user) as path:
        o = edit_options(tmp_path, {"type": "sdk", "name": "autoedit", "instance": object()}, "m", None, user, path)
        cmd = SubprocessCLITransport(prompt="x", options=o)._build_command()
    assert "SECRET" not in " ".join(cmd)
    assert cmd.count("--mcp-config") == 2 and str(path) in cmd


def test_scrub_removes_secrets_from_environ(monkeypatch):
    import os
    from autoedit import secrets_env
    monkeypatch.setenv("AUTOEDIT_MCP", json.dumps({"shop": {"type": "http", "url": "http://x"}}))
    monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k1")
    secrets_env.scrub()
    assert "AUTOEDIT_MCP" not in os.environ and "BUNDLE_SOCIAL_KEY" not in os.environ
    assert list(mcp_user.load()) == ["shop"] and secrets_env.get("BUNDLE_SOCIAL_KEY") == "k1"


def test_cli_main_scrubs_before_running(monkeypatch, capsys):
    import os
    from autoedit import cli
    monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k1")
    monkeypatch.setenv("AUTOEDIT_MCP", "{}")
    seen = {}

    async def spy(args, events):
        seen.update(os.environ)
        return 0
    monkeypatch.setattr(cli, "_setup", spy)
    assert cli.main(["setup"]) == 0
    assert "BUNDLE_SOCIAL_KEY" not in seen and "AUTOEDIT_MCP" not in seen


def test_prompt_mentions_user_tools(tmp_path):
    from test_prompt import _prep
    from autoedit.project import Project
    d = tmp_path / "p"; (d / "input").mkdir(parents=True); (d / "input" / "c.mp4").write_bytes(b"x")
    proj = Project(dir=d, niche="my-pham", clip="c.mp4")
    with_mcp = build_edit_prompt(proj, _prep(tmp_path), "", None, None, ["shop"])
    assert "mcp__shop__*" in with_mcp and "Tool bổ sung của khách" in with_mcp
    assert "Tool bổ sung" not in build_edit_prompt(proj, _prep(tmp_path), "", None, None)
    assert "Tool bổ sung" not in build_edit_prompt(proj, _prep(tmp_path), "", None, None, [])


async def test_list_tools_stdio():
    tools = await mcp_user.list_tools("echo", {"type": "stdio", "command": sys.executable, "args": [ECHO], "env": {}})
    assert [t["name"] for t in tools] == ["price"]
    assert "Giá" in tools[0]["description"]


async def test_list_tools_failure_is_agent_failed():
    with pytest.raises(AgentFailed, match="Không kết nối được MCP nope"):
        await mcp_user.list_tools("nope", {"type": "stdio", "command": "/nonexistent/bin", "args": [], "env": {}}, timeout=5)


async def test_list_tools_timeout():
    cfg = {"type": "stdio", "command": sys.executable, "args": ["-c", "import time; time.sleep(30)"], "env": {}}
    with pytest.raises(AgentFailed, match="quá 1 giây"):
        await mcp_user.list_tools("slow", cfg, timeout=1)


async def test_list_tools_http():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, ECHO, "http", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close(); break
            except OSError:
                time.sleep(0.1)
        tools = await mcp_user.list_tools("web", {"type": "http", "url": f"http://127.0.0.1:{port}/mcp",
                                                  "headers": {"X-Test": "1"}})
        assert [t["name"] for t in tools] == ["price"]
    finally:
        proc.terminate(); proc.wait(5)


def test_cli_mcp_check(monkeypatch, capsys):
    monkeypatch.setenv("AUTOEDIT_MCP", json.dumps({"echo": {"type": "stdio", "command": sys.executable, "args": [ECHO]}}))
    assert cli.main(["mcp-check", "--name", "echo"]) == 0
    ev = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert ev["type"] == "mcp_tools" and ev["name"] == "echo" and ev["tools"][0]["name"] == "price"


def test_cli_mcp_check_unknown_name(monkeypatch, capsys):
    monkeypatch.delenv("AUTOEDIT_MCP", raising=False)
    assert cli.main(["mcp-check", "--name", "x"]) == 1
    ev = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert ev["type"] == "error" and ev["code"] == "AGENT_FAILED"
