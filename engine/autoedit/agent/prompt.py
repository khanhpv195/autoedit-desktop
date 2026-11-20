import base64
import json
from pathlib import Path

from autoedit.agent.library import NICHE_NAMES, niche_intro, niche_section, skill_body
from autoedit.prep import Prepared
from autoedit.project import Project
from autoedit.transcript import format_phrases, format_words, pack_phrases


def build_edit_prompt(project: Project, prepared: Prepared, user_prompt: str, feedback: str | None,
                      previous: dict | None) -> str:
    lines = [
        f"Niche: {project.niche} ({NICHE_NAMES[project.niche]}).",
        f"Clip: {prepared.info.duration:.1f}s, {'has speech' if prepared.words else 'NO speech'}.",
        f"Logo: {'yes' if project.logo else 'no'}. Background music file: {'yes' if project.music else 'no'}.",
        "Customer request: " + (user_prompt.strip() or "(none - choose the strongest sales edit yourself)"),
    ]
    if project.script_card:
        lines.append("Chosen script card: " + json.dumps(project.script_card, ensure_ascii=False))
    if feedback:
        lines.append("This is a re-edit. Customer feedback on the previous version: " + feedback.strip())
    if previous:
        lines.append("Previous EDL: " + json.dumps(previous, ensure_ascii=False))
    lines.append("Edit the clip now, following CLAUDE.md. Finish with the finish tool.")
    return "\n".join(lines)


def build_edit_message(project: Project, prepared: Prepared, user_prompt: str, feedback: str | None,
                       previous: dict | None, agent_dir: Path) -> dict:
    """First (streamed) user message: request + skill text + full transcript + word times + keyframes, so a
    normal edit needs no Skill / get_transcript / view_frames turns."""
    request = build_edit_prompt(project, prepared, user_prompt, feedback, previous)
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
        f"## Transcript (phrases, source seconds; clip {prepared.info.duration:.2f}s)\n{phrases}",
        "## Word times (source seconds; use them for caption_fixes/emphasis `at` and for cut edges)\n" + words,
        f"## Keyframes ({n} images follow, each preceded by its source time)",
    ])
    content: list[dict] = [{"type": "text", "text": text}]
    for t, kf in zip(kf_times, prepared.keyframes):
        content.append({"type": "text", "text": f"Keyframe at {t:.2f}s"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.b64encode(kf.read_bytes()).decode()}})
    return {"type": "user", "message": {"role": "user", "content": content},
            "parent_tool_use_id": None, "session_id": "default"}
