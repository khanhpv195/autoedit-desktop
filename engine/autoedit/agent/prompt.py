import base64
import json
from pathlib import Path

from autoedit.agent.library import NICHE_NAMES, niche_intro, niche_section, skill_body
from autoedit.prep import Prepared
from autoedit.prep.keyframes import contact_sheets
from autoedit.project import Project
from autoedit.transcript import format_phrases, format_words, pack_phrases


def span_lines(prepared: Prepared) -> list[str]:
    """Where each clip sits on the joined timeline, and which b-roll images exist. All times are timeline seconds."""
    lines = []
    if len(prepared.spans) > 1:
        lines.append(f"The customer gave {len(prepared.spans)} clips, joined in this order into one timeline "
                     "(every time below is a timeline second):")
        lines += [f'Clip {i} "{n}": {a:.2f}-{b:.2f}s' for i, (n, a, b) in enumerate(prepared.spans, 1)]
    if prepared.images:
        lines.append("Images for b-roll (shown as full-frame overlays while the speech continues; add them with "
                     "`broll` {image, at, dur 1.5-4 s}): " + ", ".join(f'"{i.name}"' for i in prepared.images))
    return lines


MAX_INDIVIDUAL_IMAGES = 8      # more product images than this go to the agent as contact sheets


def _b64_image(p: Path) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(p.read_bytes()).decode()}}


def image_blocks(prepared: Prepared, detail: bool = True) -> list[dict]:
    """Content blocks showing the b-roll images. Up to 8 go one by one, each preceded by its file name; more are
    packed into 3x3 contact sheets whose tiles carry the file name drawn on them (the `broll.image` names), which
    keeps the request far below the API's per-request image limit."""
    imgs = prepared.images
    if not imgs:
        return []
    if len(imgs) <= MAX_INDIVIDUAL_IMAGES:
        out: list[dict] = [{"type": "text", "text": f"## Images for b-roll ({len(imgs)} follow, each preceded by its "
                            "file name; use that exact name in `broll.image`)"}]
        for img in imgs:
            size = f" ({img.width}x{img.height})" if detail else ""
            out.append({"type": "text", "text": f'Image "{img.name}"{size}'})
            out.append(_b64_image(img.small))
        return out
    sheets = contact_sheets([(i.name, i.small) for i in imgs], imgs[0].small.parent / "sheets")
    out = [{"type": "text", "text": f"## Images for b-roll ({len(imgs)} images in {len(sheets)} contact sheets, 3 "
            "tiles per row, read left to right then top to bottom; the label printed under each tile is its file "
            "name: use that exact name in `broll.image`)"}]
    for n, (names, path) in enumerate(sheets, 1):
        out.append({"type": "text", "text": f"Sheet {n}/{len(sheets)}: " + ", ".join(f'"{x}"' for x in names)})
        out.append(_b64_image(path))
    return out


def build_edit_prompt(project: Project, prepared: Prepared, user_prompt: str, feedback: str | None,
                      previous: dict | None, user_mcp: list[str] | None = None) -> str:
    lines = [
        f"Niche: {project.niche} ({NICHE_NAMES[project.niche]}).",
        f"Timeline: {prepared.info.duration:.1f}s, {'has speech' if prepared.words else 'NO speech'}.",
        *span_lines(prepared),
        f"Logo: {'yes' if project.logo else 'no'}. Background music file: {'yes' if project.music else 'no'}.",
        "Customer request: " + (user_prompt.strip() or "(none - choose the strongest sales edit yourself)"),
    ]
    if project.script_card:
        lines.append("Chosen script card: " + json.dumps(project.script_card, ensure_ascii=False))
    if feedback:
        lines.append("This is a re-edit. Customer feedback on the previous version: " + feedback.strip())
    if previous:
        lines.append("Previous EDL: " + json.dumps(previous, ensure_ascii=False))
    if user_mcp:
        lines.append("Tool bổ sung của khách: " + ", ".join(f"mcp__{n}__*" for n in user_mcp)
                     + " — dùng khi cần thông tin sản phẩm/thương hiệu; không bắt buộc, "
                     "không thay thế quy trình set_edl → finish.")
    lines.append("Edit the video now, following CLAUDE.md. Finish with the finish tool.")
    return "\n".join(lines)


def build_edit_message(project: Project, prepared: Prepared, user_prompt: str, feedback: str | None,
                       previous: dict | None, agent_dir: Path, user_mcp: list[str] | None = None) -> dict:
    """First (streamed) user message: request + skill text + full transcript + word times + keyframes, so a
    normal edit needs no Skill / get_transcript / view_frames turns."""
    request = build_edit_prompt(project, prepared, user_prompt, feedback, previous, user_mcp)
    phrases = format_phrases(pack_phrases(prepared.words)) or "(no speech)"
    words = format_words(prepared.words) or "(no speech)"
    n = len(prepared.keyframes)
    kf_times = [prepared.info.duration * (i + 0.5) / n for i in range(n)] if n else []
    text = "\n\n".join([
        request,
        "Everything you need is below: the cut-craft and Vietnamese sales skills, the niche hook library, "
        "the full transcript and 6 keyframes. Do not look for them again; go straight to set_edl.",
        "## Skill: video-use\n" + skill_body("video-use", agent_dir),
        "## Skill: edit-video\n" + skill_body("edit-video", agent_dir),
        "## Skill: niche-hooks (" + project.niche + ")\n" + niche_intro(agent_dir) + "\n\n"
        + niche_section(project.niche, agent_dir),
        f"## Transcript (phrases, source seconds; timeline {prepared.info.duration:.2f}s)\n{phrases}",
        "## Word times (source seconds; use them for caption_fixes/emphasis `at` and for cut edges)\n" + words,
        f"## Keyframes ({n} images follow, each preceded by its source time)",
    ])
    content: list[dict] = [{"type": "text", "text": text}]
    for t, kf in zip(kf_times, prepared.keyframes):
        content.append({"type": "text", "text": f"Keyframe at {t:.2f}s"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.b64encode(kf.read_bytes()).decode()}})
    content += image_blocks(prepared)
    return {"type": "user", "message": {"role": "user", "content": content},
            "parent_tool_use_id": None, "session_id": "default"}
