import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime

from claude_agent_sdk import AssistantMessage, RateLimitEvent, ResultMessage, TextBlock, ToolUseBlock, query

from autoedit.errors import NoAuth, RateLimited

TOOL_LABELS = {"get_transcript": "Đọc lời thoại", "view_frames": "Xem khung hình", "set_edl": "Chọn đoạn cắt",
               "render_preview": "Dựng bản xem nhanh", "finish": "Chốt bản dựng", "Skill": "Mở kiến thức dựng"}


@dataclass
class AgentOutcome:
    finished: bool
    turns: int
    error: str | None


def _iso(ts: int | None) -> str | None:
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds") if ts else None


def _clip(text: str, limit: int = 280) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if not text[limit].isspace():
        cut = cut.rsplit(None, 1)[0] if " " in cut else cut
    return cut.rstrip() + "…"


async def run_agent(session, prompt: str, options, *, query_fn=query, timeout: float = 600) -> AgentOutcome:
    turns, reset_at = 0, None
    try:
        async with asyncio.timeout(timeout):
            async for msg in query_fn(prompt=prompt, options=options):
                if isinstance(msg, RateLimitEvent):
                    info = msg.rate_limit_info
                    reset_at = _iso(info.resets_at) or reset_at
                    if info.status == "rejected":
                        raise RateLimited("Đã hết lượt Claude của gói", reset_at)
                elif isinstance(msg, AssistantMessage):
                    if msg.error == "rate_limit":
                        raise RateLimited("Đã hết lượt Claude của gói", reset_at)
                    if msg.error in ("authentication_failed", "billing_error"):
                        raise NoAuth("Tài khoản Claude chưa đăng nhập hoặc không dùng được")
                    for b in msg.content:
                        if isinstance(b, ToolUseBlock):
                            name = b.name.removeprefix("mcp__autoedit__")
                            session.events.agent(TOOL_LABELS.get(name, name), tool=name)
                        elif isinstance(b, TextBlock) and b.text.strip():
                            session.events.agent(_clip(b.text.strip()))
                elif isinstance(msg, ResultMessage):
                    turns = msg.num_turns
                    if msg.is_error:
                        print(f"agent result error: {msg.subtype} {msg.result}", file=sys.stderr)
    except TimeoutError:
        return AgentOutcome(False, turns, "timeout")
    return AgentOutcome(bool(session.finished and session.edl is not None), turns, None)
