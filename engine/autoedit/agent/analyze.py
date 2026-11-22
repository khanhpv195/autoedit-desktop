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
from autoedit.render.compose import CTA_SECONDS
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

NEVER_PROMISE = "Never promise: giảm cân, cao thêm X cm, trị mụn dứt điểm, trắng da sau N ngày, chữa bệnh."

CARDS_INTRO = f"""You suggest 3 different edit scripts for a short vertical Vietnamese sales clip.
Each card: title (≤6 words), hook (on-screen text, ≤5 words, faithful to what is said),
outline (3-5 short steps in Vietnamese), prompt (one Vietnamese instruction an editor can follow).
Base every card on lines that exist in the transcript. Use the niche library for structure and hook style.
The 3 cards must differ in hook and angle. {NEVER_PROMISE}

"""

# Shared with the chat (agent/chat.py): how a good cut is built, and what the editor can and cannot do.
EDIT_RULES = """Quality rules:
- Hook = the buyer's concrete problem or benefit in their own words, taken from the speech: a body worry
  ("Chân vòng kiềng vẫn đẹp"), a price, a result. Never a generic line ("Quần hot mùa thu đông", "Siêu phẩm",
  "Hàng mới về"). The video must open on the spoken line the hook comes from.
- Keep the speaker's order. Only the hook line may be moved to the front; after it the sentences play in the
  order they were said (no jumping back to an earlier sentence: it breaks the story and the lip sync).
- Every outline step quotes the spoken line it uses (a few words in "...") with its timeline second, e.g.
  'Mở bằng "chân vòng kiềng, đùi ếch" (88.4s)'. The prompt names the exact opening line and the closing line.
- Close on the spoken call to action or the price line, never mid-sentence.
- Shots: when the speaker is on screen, show their own picture while they talk (lip sync); cut away to another
  shot only for 1.5–4 s while they describe what that shot shows.
{full_speech}
What the editor can do (suggest nothing else - no transitions, speed ramps, beat-sync or effects):
- một video đầu ra duy nhất cho mỗi thẻ;
- cảnh xếp theo thứ tự tùy ý; số clip chỉ dùng để chỉ nguồn của cảnh ("cảnh xoay người ở clip 2");
- tiếng của một clip chạy liền dưới hình của clip khác ("lồng tiếng clip 2"); tắt tiếng một clip ("bỏ tiếng clip 1");
- một hook text tối đa 5 từ trong 2.5 s đầu;
{broll}
- chữ kêu gọi (CTA) ở góc dưới trái trong {cta:g} s cuối, trùng câu chốt;
- không bịa thông tin sản phẩm (chất liệu, giá, size, khuyến mãi) ngoài lời thoại và thông tin khách nhập."""

INSTRUCTIONS = CARDS_INTRO + EDIT_RULES

FULL_SPEECH = """- Clip {silent} has no speech and clip {talk} has the talking: card 1 MUST be "Giữ trọn lời":
  picture of clip {silent} runs first, then clip {talk}'s own picture at the matching moment; sound = clip {talk}
  in full, from its first word to its last word {last!r}, no sentence cut; clip {silent}'s sound muted. Its
  prompt must say: "clip {silent} chạy, lồng tiếng clip {talk} đầy đủ đến từ cuối cùng {last!r}, bỏ tiếng clip
  {silent}". Its length is the speech length, whatever the target. Its opening line is fixed (nothing is
  moved), so its hook is the strongest buyer problem or benefit said ANYWHERE in the speech (e.g. a body worry
  or the price), not the generic first line ("bản mới", "rất hot"). Cards 2 and 3 are shorter cut-downs that
  still use clip {talk}'s sound only and mute clip {silent}; their hooks differ from card 1's.
"""


BROLL_IMAGES = "- b-roll ảnh sản phẩm 1.5–4 s mỗi ảnh, tối đa 1 ảnh mỗi 3 s;"
BROLL_NONE = "- Không có ảnh sản phẩm: không nhắc tới ảnh hay b-roll ảnh; muốn đổi hình thì dùng cảnh khác trong clip;"

VISUAL_HINT = ("No speech: suggest visual-first scripts (Dựng theo hình) - open on the clearest full-body or moving "
               "shot of the product, short shots of 1.2-3 s, product photos as b-roll after the product is seen, "
               "hook text only about what is visible.")


def full_speech_rule(prepared: Prepared, template: str | None = None) -> str:
    """The "Giữ trọn lời" card: one clip without speech (room noise) and one clip with all the talking."""
    if len(prepared.spans) < 2:
        return ""
    counts = []
    for i, (_, a, b) in enumerate(prepared.spans, 1):
        own = [w for w in prepared.words if a - 1e-6 <= (w.start + w.end) / 2 < b]
        counts.append((i, own))
    talk = [(i, own) for i, own in counts if len(own) >= 3]
    silent = [i for i, own in counts if len(own) < 3]
    if len(talk) != 1 or not silent:
        return ""
    t, own = talk[0]
    return (template or FULL_SPEECH).format(silent=silent[0], talk=t, last=own[-1].text)


def project_lines(project: Project | None, has_speech: bool) -> list[str]:
    lines = []
    if project is not None:
        target = project.target_range()
        lines.append(f"Target length: {target[0]:.0f}–{target[1]:.0f}s." if target else
                     "Target length: not given. Choose each card's length from the content and end its outline "
                     "with the length and why, e.g. \"Dài ~40s: đủ 4 ý chính\".")
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
    text = (f"{INSTRUCTIONS.format(broll=broll, full_speech=full_speech_rule(prepared), cta=CTA_SECONDS)}\n\nNiche: {niche} ({NICHE_NAMES[niche]})\n"
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


async def run_structured(message: dict, agent_dir: Path, schema: dict, query_fn=query) -> dict | None:
    """One Claude call without tools whose answer must match `schema`; rate-limit / auth errors raised as ours."""
    async def stream():
        yield message

    opts = plain_options(agent_dir, model(), max_turns=3,
                         output_format={"type": "json_schema", "schema": schema})
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
    return structured if isinstance(structured, dict) else None


async def run_analyze(prepared: Prepared, niche: str, agent_dir: Path, exclude: list[str] | None = None,
                      *, project: Project | None = None, query_fn=query) -> list[dict]:
    message = build_analyze_message(prepared, niche, agent_dir, exclude or [], project)
    structured = await run_structured(message, agent_dir, CARDS_SCHEMA, query_fn)
    cards = (structured or {}).get("cards")
    if not cards or len(cards) != 3 or not all({"title", "hook", "outline", "prompt"} <= set(c) for c in cards):
        raise AgentFailed("AI không gợi ý được kịch bản, thử lại")
    return cards
