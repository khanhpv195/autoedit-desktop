import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime

from claude_agent_sdk import AssistantMessage, RateLimitEvent, ResultMessage, TextBlock, ToolUseBlock, query

from autoedit.agent.sdk_errors import NO_AUTH_MSG, RATE_MSG, classify_result, classify_sdk_error
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


async def run_agent(session, prompt, options, *, query_fn=query, timeout: float = 600, on_message=None) -> AgentOutcome:
    """prompt: a string or a streamed user-message dict. Stops reading as soon as `finish` succeeded."""
    turns, reset_at = 0, None

    async def stream():
        yield prompt

    def done() -> bool:
        return bool(session.finished and session.edl is not None)

    it = None
    try:
        async with asyncio.timeout(timeout):
            it = query_fn(prompt=stream() if isinstance(prompt, dict) else prompt, options=options)
            async for msg in it:
                if on_message:
                    on_message(msg)
                if isinstance(msg, RateLimitEvent):
                    info = msg.rate_limit_info
                    reset_at = _iso(info.resets_at) or reset_at
                    if info.status == "rejected" and not done():
                        raise RateLimited(RATE_MSG, reset_at)
                elif isinstance(msg, AssistantMessage):
                    if msg.error == "rate_limit" and not done():
                        raise RateLimited(RATE_MSG, reset_at)
                    if msg.error in ("authentication_failed", "billing_error") and not done():
                        raise NoAuth(NO_AUTH_MSG)
                    if any(isinstance(b, ToolUseBlock) for b in msg.content):
                        turns += 1      # the stream is closed before ResultMessage, so count tool-call turns ourselves
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
                        err = classify_result(msg, reset_at)
                        if err and not done():
                            raise err
                if done():
                    break
                if getattr(session, "aborted", False):
                    return AgentOutcome(False, turns, "aborted")
    except TimeoutError:
        return AgentOutcome(done(), turns, None if done() else "timeout")
    except Exception as e:
        if done():          # the edit is complete: whatever the CLI did afterwards (max_turns, crash) is moot
            print(f"ignored SDK error after finish: {type(e).__name__}: {e}", file=sys.stderr)
            return AgentOutcome(True, turns, None)
        err = classify_sdk_error(e, reset_at)
        if err is not None:
            raise err from e
        raise
    finally:
        aclose = getattr(it, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:
                pass
    return AgentOutcome(done(), turns, None)
