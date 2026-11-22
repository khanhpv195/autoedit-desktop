"""Chat with the customer before an edit: agree the length, hook, CTA and what to keep, then hand back a plan.

One call = one turn. The whole conversation lives in <project>/chat.json and is sent back to Claude every turn
(no SDK session to lose when the app restarts). The edit itself starts only when the customer presses
"Bắt đầu edit" on the latest plan (the app then saves plan.prompt and plan.target_seconds and runs `edit`).
"""
import base64
import json
import time
from pathlib import Path

from claude_agent_sdk import query

from autoedit.agent.analyze import (BROLL_IMAGES, BROLL_NONE, EDIT_RULES, NEVER_PROMISE, VISUAL_HINT,
                                    full_speech_rule, run_structured)
from autoedit.agent.library import NICHE_NAMES, niche_section
from autoedit.agent.references import reference_text
from autoedit.agent.prompt import image_blocks, span_lines
from autoedit.errors import AgentFailed, BadInput
from autoedit.fsutil import atomic_write_text
from autoedit.prep import Prepared
from autoedit.project import Project
from autoedit.render.compose import CTA_SECONDS
from autoedit.transcript import format_phrases, pack_phrases

CHAT_FILE = "chat.json"
MAX_MESSAGE = 2000
MAX_SUGGESTIONS = 4
MAX_HISTORY = 40        # messages sent back to Claude; older ones are dropped from the prompt (kept on disk)

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 7},
        "prompt": {"type": "string"},
        "target_seconds": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        "length_source": {"type": "string", "enum": ["customer", "ai"]},
        "length_reason": {"type": "string"},
        "hook": {"type": "string"},
        "cta": {"type": "string"},
    },
    "required": ["summary", "prompt", "target_seconds", "length_source", "length_reason", "hook", "cta"],
    "additionalProperties": False,
}

CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "suggestions": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_SUGGESTIONS},
        "plan": {"anyOf": [{"type": "null"}, PLAN_SCHEMA]},
    },
    "required": ["reply", "suggestions", "plan"],
    "additionalProperties": False,
}

CHAT_INTRO = f"""You are the editing assistant inside AutoEdit, chatting in Vietnamese with a shop owner about
their clip BEFORE it is edited. You do not edit now: you agree the plan; the editor (another agent with the
same rules) cuts the video after the customer presses "Bắt đầu edit".

Each turn answer as JSON:
- reply: Vietnamese, warm and short (at most 90 words, plain text, no markdown headings). Address the customer
  as "anh/chị". Quote the spoken lines you mean with their timeline second ("chân vòng kiềng" 88.4s).
- suggestions: 2-4 quick replies the customer can tap, written as the customer would say them (each at most
  40 characters), e.g. "Như video mẫu", "Giữ trọn lời", "Rút còn ~30s", "Mở bằng câu giá". [] only when a plan is given.
- plan: null while something important is still open. When the customer has answered enough (or says ok / làm
  đi / được), give the full plan and say in reply that they can press "Bắt đầu edit" or keep chatting to change
  it. A new plan replaces the previous one; always give the whole plan, never a diff.

Opening turn (the customer message is empty): in 2-3 sentences say what the clips contain (who talks, the main
points, how long the speech is), offer 2-3 directions as suggestions, and ask the single most important
question. Do not give a plan in the opening turn.

What to settle, asking at most 2 questions per turn and only about what is still unclear: the length, the hook
line, which lines or clips to keep or drop, the CTA, captions (fix misheard words, highlight words, position top/middle/bottom, size small/normal/large). Propose
concrete options from the transcript instead of open questions. Never ask about something the customer already
said, and never ask about things the editor cannot do.

Length: if the customer names a length, the plan uses it (length_source "customer", target_seconds = what they
said, e.g. 30s -> [27, 33]). If not, choose it yourself from the content: the speech worth keeping, the number
of key points, TikTok/Reels (most sales clips 20-60 s, never padded) -> length_source "ai", and say the chosen
length and why in reply and in length_reason (e.g. "42s: giữ đủ 4 ý vòng kiềng, chất vải, giá, free ship").
Keeping every sentence ("giữ trọn lời") means target_seconds = the speech length.

plan fields:
- summary: 3-6 short Vietnamese lines for the customer, the first one "Thời lượng: ~Xs — <lý do>", then
  "Hook: ...", "Mở bằng: "..." (s)", "Giữ / bỏ: ...", "Kết: "..." (s)", "CTA: ...".
- prompt: one complete Vietnamese instruction for the editor: the length, the hook text, the exact opening and
  closing lines with their seconds, which clips / sound to keep or mute, the CTA, any caption fix. It must
  stand alone (the editor does not see this chat).
- hook: on-screen hook text, at most 5 words, faithful to what is said. cta: at most 30 characters.

Fixed by the app (mention only if asked): the hook card never covers the speaker's face; the CTA sits at the
bottom-left for the last {CTA_SECONDS:g} s with an arrow to the product link; captions are burned in
automatically from the speech. {NEVER_PROMISE}

"""

FULL_SPEECH_CHAT = """- Clip {silent} has no speech and clip {talk} has all the talking: this is the shape of "Mẫu 1" in the
  video mẫu. Offer "Như video mẫu" first: clip {talk}'s picture as the base (lip-synced), clip {silent} muted and
  used as 2.5-3.5 s cutaways about every 8-10 s, the strongest buyer problem/benefit line moved to the front as
  the hook, then the speaker's order, only filler cut, every product fact kept, ending on the last word
  {last!r}. Also offer "Giữ trọn lời" (picture of clip {silent} first, then clip {talk}; sound = clip {talk} in
  full to {last!r}; length = the speech length) for a customer who wants every word.
"""


def chat_path(project_dir: Path) -> Path:
    return Path(project_dir) / CHAT_FILE


def load_history(project_dir: Path) -> list[dict]:
    """The saved messages; [] when there is no chat yet or the file is unreadable."""
    try:
        data = json.loads(chat_path(project_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    msgs = data.get("messages") if isinstance(data, dict) else None
    return [m for m in msgs if isinstance(m, dict) and m.get("role") in ("user", "assistant")] if isinstance(msgs, list) else []


def save_history(project_dir: Path, messages: list[dict]) -> None:
    atomic_write_text(chat_path(project_dir), json.dumps({"v": 1, "messages": messages}, ensure_ascii=False, indent=2))


def _speech_seconds(prepared: Prepared) -> float:
    return round(sum(w.end - w.start for w in prepared.words), 1)


def _history_text(history: list[dict]) -> str:
    lines = []
    for m in history[-MAX_HISTORY:]:
        if m["role"] == "user":
            lines.append(f"KHÁCH: {m.get('text') or '(mở đầu)'}")
        else:
            lines.append(f"BẠN: {m.get('text', '')}")
            if m.get("plan"):
                lines.append("BẠN (kế hoạch đã đưa): " + json.dumps(m["plan"], ensure_ascii=False))
    return "\n".join(lines)


def build_chat_message(project: Project, prepared: Prepared, history: list[dict], text: str,
                       agent_dir: Path) -> dict:
    rules = EDIT_RULES.format(broll=BROLL_IMAGES if prepared.images else BROLL_NONE,
                              full_speech=full_speech_rule(prepared, FULL_SPEECH_CHAT), cta=CTA_SECONDS)
    facts = [
        f"Niche: {project.niche} ({NICHE_NAMES[project.niche]}).",
        f"Timeline: {prepared.info.duration:.1f}s; speech about {_speech_seconds(prepared):.0f}s"
        if prepared.words else f"Timeline: {prepared.info.duration:.1f}s; NO speech.",
        *span_lines(prepared),
        f"Product photos: {len(prepared.images)}. Logo: {'yes' if project.logo else 'no'}. "
        f"Music file: {'yes' if project.music else 'no'}.",
        f"Default CTA text: {project.cta_text}",
    ]
    if not prepared.words:
        facts.append(VISUAL_HINT)
    if project.voiceover_on:
        facts.append("Lồng tiếng AI: bật (tiếng gốc tắt; giọng AI đọc lời viết từ thông tin sản phẩm). "
                     "Thông tin sản phẩm: " + (project.product_info.strip() or "(trống)"))
    elif project.product_info.strip():
        facts.append("Thông tin sản phẩm (khách nhập): " + project.product_info.strip())
    transcript = format_phrases(pack_phrases(prepared.words)) or "(no speech)"
    body = "\n\n".join([
        CHAT_INTRO + rules,
        "Niche library:\n" + niche_section(project.niche, agent_dir),
        "Video mẫu (edits the customer approved; copy the structure, not the facts):\n"
        + reference_text(agent_dir, project.niche, project.dir),
        "\n".join(facts),
        "Transcript (timeline seconds):\n" + transcript,
        "Conversation so far:\n" + (_history_text(history) or "(none)"),
        "New customer message: " + (text or "(empty: this is the opening turn)"),
    ])
    content = [{"type": "text", "text": body}]
    for kf in prepared.keyframes[:3]:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.b64encode(kf.read_bytes()).decode()}})
    content += image_blocks(prepared, detail=False)
    return {"type": "user", "message": {"role": "user", "content": content},
            "parent_tool_use_id": None, "session_id": "default"}


def clean_reply(raw: dict | None) -> dict:
    """Check and tidy Claude's turn: a reply is required, suggestions are trimmed, a broken plan is an error."""
    if not isinstance(raw, dict) or not str(raw.get("reply") or "").strip():
        raise AgentFailed("AI không trả lời được, thử gửi lại")
    sugg = [str(x).strip()[:60] for x in raw.get("suggestions") or [] if str(x).strip()][:MAX_SUGGESTIONS]
    plan = raw.get("plan")
    if plan is not None:
        if not isinstance(plan, dict) or not str(plan.get("prompt") or "").strip():
            raise AgentFailed("AI đưa kế hoạch thiếu mô tả, thử gửi lại")
        t = plan.get("target_seconds")
        if not (isinstance(t, list) and len(t) == 2 and all(isinstance(x, (int, float)) for x in t)):
            raise AgentFailed("AI đưa kế hoạch thiếu thời lượng, thử gửi lại")
        lo, hi = sorted(float(x) for x in t)
        if not 0 < hi <= 600:
            raise AgentFailed("AI đưa thời lượng không hợp lệ, thử gửi lại")
        plan = {
            "summary": [str(x).strip() for x in plan.get("summary") or [] if str(x).strip()][:7],
            "prompt": str(plan["prompt"]).strip(),
            "target_seconds": [round(max(lo, 1.0), 1), round(hi, 1)],
            "length_source": "customer" if plan.get("length_source") == "customer" else "ai",
            "length_reason": str(plan.get("length_reason") or "").strip(),
            "hook": str(plan.get("hook") or "").strip(),
            "cta": str(plan.get("cta") or "").strip()[:30],
        }
        sugg = []
    return {"reply": str(raw["reply"]).strip(), "suggestions": sugg, "plan": plan}


async def run_chat_turn(project: Project, prepared: Prepared, text: str, agent_dir: Path,
                        *, query_fn=query, now=time.time) -> dict:
    """Send one customer message (empty = opening turn), save both sides, return the assistant message."""
    text = (text or "").strip()
    if len(text) > MAX_MESSAGE:
        raise BadInput(f"Tin nhắn tối đa {MAX_MESSAGE} ký tự")
    history = load_history(project.dir)
    if not text and history:
        raise BadInput("Tin nhắn trống")
    message = build_chat_message(project, prepared, history, text, agent_dir)
    turn = clean_reply(await run_structured(message, agent_dir, CHAT_SCHEMA, query_fn))
    ts = round(now(), 3)
    # the opening turn has no customer text: only the assistant's greeting is kept
    added = ([{"role": "user", "text": text, "ts": ts}] if text else []) + [{"role": "assistant", "text": turn["reply"],
                                                         "suggestions": turn["suggestions"], "plan": turn["plan"],
                                                         "ts": ts}]
    save_history(project.dir, load_history(project.dir) + added)
    return added[-1]
