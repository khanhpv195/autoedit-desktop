"""Customer MCP servers: AUTOEDIT_MCP (set by the app, never persisted here) -> SDK config; mcp-check."""
import asyncio
import json
import os
import re
import sys

from autoedit.errors import AgentFailed

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
MAX_SERVERS = 10


def _skip(name, why: str) -> None:
    print(f"MCP {name!r} bị bỏ qua: {why}", file=sys.stderr)    # names only, never values


def _str_map(v) -> dict[str, str]:
    return {str(k): str(x) for k, x in v.items()} if isinstance(v, dict) else {}


def load(env=None) -> dict[str, dict]:
    env = os.environ if env is None else env
    raw = env.get("AUTOEDIT_MCP")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except ValueError:
        print("AUTOEDIT_MCP không đọc được, bỏ qua MCP của khách", file=sys.stderr)
        return {}
    out: dict[str, dict] = {}
    for name, cfg in data.items():
        if not isinstance(name, str) or not NAME_RE.match(name) or name == "autoedit":
            _skip(name, "tên không hợp lệ")
        elif not isinstance(cfg, dict):
            _skip(name, "cấu hình sai")
        elif cfg.get("type") == "stdio" and isinstance(cfg.get("command"), str) and cfg["command"]:
            args = cfg.get("args")
            out[name] = {"type": "stdio", "command": cfg["command"],
                         "args": [str(a) for a in args] if isinstance(args, list) else [],
                         "env": _str_map(cfg.get("env"))}
        elif cfg.get("type") == "http" and isinstance(cfg.get("url"), str) and cfg["url"]:
            out[name] = {"type": "http", "url": cfg["url"], "headers": _str_map(cfg.get("headers"))}
        else:
            _skip(name, "thiếu lệnh hoặc url")
        if len(out) >= MAX_SERVERS:
            break
    return out


def _leaf(e: BaseException) -> BaseException:
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


async def _list(cfg: dict) -> list[dict]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared._httpx_utils import create_mcp_http_client

    async def talk(read, write) -> list[dict]:
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.list_tools()
            return [{"name": t.name, "description": t.description or ""} for t in res.tools]

    if cfg["type"] == "stdio":
        params = StdioServerParameters(command=cfg["command"], args=cfg.get("args") or [], env=cfg.get("env") or None)
        with open(os.devnull, "w") as quiet:     # a customer server's own stderr may echo its secrets
            async with stdio_client(params, errlog=quiet) as (read, write):
                return await talk(read, write)
    async with create_mcp_http_client(headers=cfg.get("headers") or None) as http:
        async with streamable_http_client(cfg["url"], http_client=http) as (read, write):
            return await talk(read, write)


async def list_tools(name: str, cfg: dict, timeout: float = 20) -> list[dict]:
    try:
        async with asyncio.timeout(timeout):
            return await _list(cfg)
    except TimeoutError:
        raise AgentFailed(f"Không kết nối được MCP {name}: quá {int(timeout)} giây") from None
    except Exception as e:
        e = _leaf(e)
        raise AgentFailed(f"Không kết nối được MCP {name}: {type(e).__name__}: {str(e)[:200]}") from None
