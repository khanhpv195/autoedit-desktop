import base64
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ResultMessage, query

from autoedit.agent.library import NICHE_NAMES, niche_section
from autoedit.agent.options import model, plain_options
from autoedit.errors import AgentFailed, NoAuth, RateLimited
from autoedit.prep import Prepared
from autoedit.transcript import format_phrases, pack_phrases

CARDS_SCHEMA = {
    "type": "object",
    "properties": {"cards": {"type": "array", "minItems": 3, "maxItems": 3, "items": {
        "type": "object",
        "properties": {"title": {"type": "string"}, "hook": {"type": "string"},
                       "outline": {"type": "array", "items": {"type": "string"}}, "prompt": {"type": "string"}},
        "required": ["title", "hook", "outline", "prompt"], "additionalProperties": False}}},
    "required": ["cards"], "additionalProperties": False,
}

INSTRUCTIONS = """You suggest 3 different edit scripts for a short vertical Vietnamese sales clip.
Each card: title (≤6 words), hook (on-screen text, ≤5 words, faithful to what is said),
outline (3-5 short steps in Vietnamese), prompt (one Vietnamese instruction an editor can follow,
mentioning which spoken line opens the video). Base every card on lines that exist in the transcript.
Use the niche library for structure and hook style. The 3 cards must differ in hook and order.
Never promise: giảm cân, cao thêm X cm, trị mụn dứt điểm, trắng da sau N ngày, chữa bệnh."""


def build_analyze_message(prepared: Prepared, niche: str, agent_dir: Path, exclude: list[str]) -> dict:
    transcript = format_phrases(pack_phrases(prepared.words)) or "(no speech - suggest visual-first scripts)"
    text = (f"{INSTRUCTIONS}\n\nNiche: {niche} ({NICHE_NAMES[niche]})\n"
            f"Niche library:\n{niche_section(niche, agent_dir)}\n\n"
            f"Clip duration: {prepared.info.duration:.1f}s\nTranscript:\n{transcript}\n")
    if exclude:
        text += "\nDo not repeat these earlier cards: " + "; ".join(exclude) + "\n"
    content = [{"type": "text", "text": text}]
    for kf in prepared.keyframes[:3]:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.b64encode(kf.read_bytes()).decode()}})
    return {"type": "user", "message": {"role": "user", "content": content},
            "parent_tool_use_id": None, "session_id": "default"}


async def run_analyze(prepared: Prepared, niche: str, agent_dir: Path, exclude: list[str] | None = None,
                      *, query_fn=query) -> list[dict]:
    message = build_analyze_message(prepared, niche, agent_dir, exclude or [])

    async def stream():
        yield message

    opts = plain_options(agent_dir, model(), max_turns=3,
                         output_format={"type": "json_schema", "schema": CARDS_SCHEMA})
    structured = None
    async for msg in query_fn(prompt=stream(), options=opts):
        if isinstance(msg, AssistantMessage):
            if msg.error == "rate_limit":
                raise RateLimited("Đã hết lượt Claude của gói")
            if msg.error in ("authentication_failed", "billing_error"):
                raise NoAuth("Tài khoản Claude không dùng được")
        elif isinstance(msg, ResultMessage):
            structured = msg.structured_output
    cards = (structured or {}).get("cards") if isinstance(structured, dict) else None
    if not cards or len(cards) != 3 or not all({"title", "hook", "outline", "prompt"} <= set(c) for c in cards):
        raise AgentFailed("AI không gợi ý được kịch bản, thử lại")
    return cards
