"""One-shot AI caption for a finished run (no tools), same error mapping as analyze."""
import json
from pathlib import Path

from claude_agent_sdk import AssistantMessage, RateLimitEvent, ResultMessage, TextBlock, query

from autoedit.agent.library import NICHE_NAMES
from autoedit.agent.options import model, plain_options
from autoedit.agent.runner import _iso
from autoedit.agent.sdk_errors import NO_AUTH_MSG, RATE_MSG, classify_result, classify_sdk_error
from autoedit.errors import AgentFailed, BadInput, NoAuth, RateLimited
from autoedit.project import Project
from autoedit.transcript import format_phrases, pack_phrases, words_from_json

INSTRUCTIONS = """Viết caption đăng TikTok/Reels/Shorts cho video bán hàng của một shop Việt Nam.
Yêu cầu: tiếng Việt, tối đa 300 ký tự, gồm 1-2 câu mô tả hấp dẫn, một câu kêu gọi hành động ngắn
(ví dụ "Bấm giỏ hàng nhé"), rồi 3-5 hashtag. Chỉ dùng thông tin có trong lời thoại hoặc tóm tắt, không bịa giá hay công dụng.
Không hứa hẹn quá đà: giảm cân, cao thêm X cm, trị mụn dứt điểm, trắng da sau N ngày, chữa bệnh, an toàn tuyệt đối.
Chỉ trả về đúng nội dung caption, không giải thích, không ngoặc kép."""


def _transcript(project: Project) -> str:
    f = project.work_dir / "transcript.json"
    try:
        words = words_from_json(json.loads(f.read_text(encoding="utf-8"))["words"])
    except (OSError, ValueError, KeyError, TypeError):
        return ""
    return " ".join(p.text for p in pack_phrases(words))


def _hook(project: Project, run: int) -> str:
    try:
        edl = json.loads((project.dir / "runs" / str(run) / "edl.json").read_text(encoding="utf-8"))
        return ((edl.get("hook") or {}).get("text")) or ""
    except (OSError, ValueError, AttributeError):
        return ""


def build_prompt(project: Project, run: int) -> str:
    entry = next((r for r in project.runs if r.get("n") == run), None)
    if entry is None:
        raise BadInput(f"Không thấy bản dựng {run}")
    summary = "; ".join(entry.get("summary") or [])
    return (f"{INSTRUCTIONS}\n\nNgành: {NICHE_NAMES[project.niche]}\nTóm tắt bản dựng: {summary or '(không có)'}\n"
            f"Chữ mở đầu (hook): {_hook(project, run) or '(không có)'}\n"
            f"Lời thoại: {_transcript(project) or '(không có lời thoại)'}\n")


def clean(text: str) -> str:
    t = text.strip().strip("`").strip()
    if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'“”":
        t = t[1:-1].strip()
    return t[:2200]


async def make_caption(project: Project, run: int, agent_dir: Path, *, query_fn=query) -> str:
    opts = plain_options(agent_dir, model(), max_turns=2)
    prompt = build_prompt(project, run)
    texts: list[str] = []
    result, reset_at = None, None
    try:
        async for msg in query_fn(prompt=prompt, options=opts):
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
                texts += [b.text for b in msg.content if isinstance(b, TextBlock)]
            elif isinstance(msg, ResultMessage):
                err = classify_result(msg, reset_at)
                if err:
                    raise err
                result = msg.result
    except Exception as e:
        err = classify_sdk_error(e, reset_at)
        if err is not None:
            raise err from e
        raise
    text = clean(result or (texts[-1] if texts else ""))
    if not text:
        raise AgentFailed("AI không viết được caption, thử lại")
    return text
