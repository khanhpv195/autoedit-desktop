import base64
from pathlib import Path

from claude_agent_sdk import AssistantMessage, RateLimitEvent, ResultMessage, query

from autoedit.agent.library import NICHE_NAMES, niche_section
from autoedit.agent.options import model, plain_options
from autoedit.agent.prompt import image_blocks, span_lines
from autoedit.agent.runner import _iso
from autoedit.agent.sdk_errors import NO_AUTH_MSG, RATE_MSG, classify_result, classify_sdk_error
from autoedit.errors import AgentFailed, NoAuth, RateLimited
from autoedit.prep import Prepared
from autoedit.project import Project
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
If several clips are given, say in each card how to order and mix their shots; only when images are given,
say where they work as b-roll while the speech continues.
Never promise: giảm cân, cao thêm X cm, trị mụn dứt điểm, trắng da sau N ngày, chữa bệnh.

What the editor can do (suggest nothing else - no transitions, speed ramps, beat-sync or effects):
- một video đầu ra duy nhất cho mỗi thẻ;
- cảnh xếp theo thứ tự tùy ý; số clip chỉ dùng để chỉ nguồn của cảnh ("cảnh xoay người ở clip 2");
- một hook text tối đa 5 từ trong 2.5 s đầu;
{broll}
- chữ kêu gọi (CTA) trong 2 s cuối;
- không bịa thông tin sản phẩm (chất liệu, giá, size, khuyến mãi) ngoài lời thoại và thông tin khách nhập."""


BROLL_IMAGES = "- b-roll ảnh sản phẩm 1.5–4 s mỗi ảnh, tối đa 1 ảnh mỗi 3 s;"
BROLL_NONE = "- Không có ảnh sản phẩm: không nhắc tới ảnh hay b-roll ảnh; muốn đổi hình thì dùng cảnh khác trong clip;"

VISUAL_HINT = ("No speech: suggest visual-first scripts (Dựng theo hình) - open on the clearest full-body or moving "
               "shot of the product, short shots of 1.2-3 s, product photos as b-roll after the product is seen, "
               "hook text only about what is visible.")


def project_lines(project: Project | None, has_speech: bool) -> list[str]:
    lines = []
    if project is not None:
        lo, hi = project.length_range
        lines.append(f"Target length: {lo:.0f}–{hi:.0f}s.")
    if not has_speech:
        lines.append(VISUAL_HINT)
    if project is not None and project.voiceover_on:
        lines.append("Lồng tiếng AI: bật (tiếng gốc bị tắt; một giọng đọc AI đọc lời viết từ thông tin sản phẩm). "
                     "Thông tin sản phẩm (khách nhập): " + (project.product_info.strip() or "(trống)"))
    return lines


def build_analyze_message(prepared: Prepared, niche: str, agent_dir: Path, exclude: list[str],
                          project: Project | None = None) -> dict:
    transcript = format_phrases(pack_phrases(prepared.words)) or "(no speech - suggest visual-first scripts)"
    broll = BROLL_IMAGES if prepared.images else BROLL_NONE
    text = (f"{INSTRUCTIONS.format(broll=broll)}\n\nNiche: {niche} ({NICHE_NAMES[niche]})\n"
            f"Niche library:\n{niche_section(niche, agent_dir)}\n\n"
            f"Total duration: {prepared.info.duration:.1f}s\n")
    extra = project_lines(project, bool(prepared.words))
    if extra:
        text += "\n".join(extra) + "\n"
    spans = span_lines(prepared)
    if spans:
        text += "\n".join(spans) + "\n"
    text += f"Transcript (timeline seconds):\n{transcript}\n"
    if exclude:
        text += "\nDo not repeat these earlier cards: " + "; ".join(exclude) + "\n"
    content = [{"type": "text", "text": text}]
    for kf in prepared.keyframes[:3]:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.b64encode(kf.read_bytes()).decode()}})
    content += image_blocks(prepared, detail=False)
    return {"type": "user", "message": {"role": "user", "content": content},
            "parent_tool_use_id": None, "session_id": "default"}


async def run_analyze(prepared: Prepared, niche: str, agent_dir: Path, exclude: list[str] | None = None,
                      *, project: Project | None = None, query_fn=query) -> list[dict]:
    message = build_analyze_message(prepared, niche, agent_dir, exclude or [], project)

    async def stream():
        yield message

    opts = plain_options(agent_dir, model(), max_turns=3,
                         output_format={"type": "json_schema", "schema": CARDS_SCHEMA})
    structured, reset_at = None, None
    try:
        async for msg in query_fn(prompt=stream(), options=opts):
            if isinstance(msg, RateLimitEvent):
                info = msg.rate_limit_info
                reset_at = _iso(info.resets_at) or reset_at
                if info.status == "rejected":
                    raise RateLimited(RATE_MSG, reset_at)
            elif isinstance(msg, AssistantMessage):
                if msg.error == "rate_limit":
                    raise RateLimited(RATE_MSG, reset_at)
                if msg.error in ("authentication_failed", "billing_error"):
                    raise NoAuth(NO_AUTH_MSG)
            elif isinstance(msg, ResultMessage):
                err = classify_result(msg, reset_at)
                if err:
                    raise err
                structured = msg.structured_output
    except Exception as e:
        err = classify_sdk_error(e, reset_at)
        if err is not None:
            raise err from e
        raise
    cards = (structured or {}).get("cards") if isinstance(structured, dict) else None
    if not cards or len(cards) != 3 or not all({"title", "hook", "outline", "prompt"} <= set(c) for c in cards):
        raise AgentFailed("AI không gợi ý được kịch bản, thử lại")
    return cards
