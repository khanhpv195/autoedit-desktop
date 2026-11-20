import json

from autoedit.agent.library import NICHE_NAMES
from autoedit.prep import Prepared
from autoedit.project import Project


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
