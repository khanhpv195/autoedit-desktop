"""Video mẫu the customer saved from the app ("Lưu làm mẫu").

A reference is one Markdown file in <app data>/references/: the clips, the request, which spoken lines were kept
or dropped and the EDL of an edit the customer liked. The chat, cards and edit prompts show the built-in
reference-edits skill plus the newest saved references (same niche first), so the AI copies their structure.
The run gets `"reference": <id>` in project.json so the app can show it as saved.
"""
import json
import os
import re
import time
from pathlib import Path

from autoedit.bins import app_data_dir
from autoedit.errors import BadInput
from autoedit.fsutil import atomic_write_text
from autoedit.prep import Prepared
from autoedit.project import Project, update_project
from autoedit.transcript import pack_phrases

MAX_IN_PROMPT = 2           # saved references shown to the AI (newest, same niche first)
MAX_CHARS = 7000            # per reference in a prompt
_ID = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")


def refs_dir() -> Path:
    if env := os.environ.get("AUTOEDIT_REFS_DIR"):
        return Path(env)
    return app_data_dir() / "references"


def reference_id(project: Project, run: int) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]", "_", project.dir.name)[:100] or "project"
    return f"{stem}-run{run}"


def _path(ref_id: str, root: Path | None) -> Path:
    if not _ID.match(ref_id or ""):
        raise BadInput("Mã video mẫu không hợp lệ")
    return (root or refs_dir()) / f"{ref_id}.md"


def _inside(t: float, ranges: list[tuple[float, float]]) -> bool:
    return any(a - 1e-6 <= t <= b + 1e-6 for a, b in ranges)


def build_reference(project: Project, run: dict, edl: dict, prepared: Prepared) -> str:
    """The Markdown body the AI reads: input shape, request, kept/dropped lines, EDL."""
    name = project.name or project.dir.name
    lines = [f"## Mẫu của khách: \"{name}\" ({project.niche})", "", "Input:"]
    for i, (clip, a, b) in enumerate(prepared.spans or [("clip", 0.0, prepared.info.duration)], 1):
        own = [w for w in prepared.words if a - 1e-6 <= (w.start + w.end) / 2 < b]
        speech = f"speech {own[0].start:.1f}-{own[-1].end:.1f} s" if len(own) >= 3 else "no speech"
        lines.append(f"- Clip {i}: {a:.1f}-{b:.1f} s, {speech}")
    request = (run.get("prompt") or project.prompt or "").strip()
    if request:
        lines.append(f"- Customer request: {request}")
    if run.get("feedback"):
        lines.append(f"- Re-edit feedback: {run['feedback']}")
    if project.target_seconds:
        lines.append(f"- Target length: {project.target_seconds[0]:g}-{project.target_seconds[1]:g} s")
    keep = [(float(r["start"]), float(r["end"])) for r in edl.get("keep") or []
            if isinstance(r, dict) and "start" in r and "end" in r]
    out_len = sum(b - a for a, b in keep)
    lines += ["", f"Result: {len(keep)} picture ranges, about {out_len:.0f} s."]
    if run.get("summary"):
        lines += ["What the editor did:"] + [f"- {s}" for s in run["summary"]]
    phrases = pack_phrases(prepared.words)
    if phrases and not edl.get("audio_source"):
        lines += ["", "Spoken lines ([giữ] kept, [bỏ] dropped; timeline seconds):"]
        for p in phrases:
            mark = "giữ" if _inside((p.start + p.end) / 2, keep) else "bỏ"
            lines.append(f"- [{mark}] {p.start:.1f} {p.text}")
    elif phrases:
        lines += ["", f"Sound: clip {edl['audio_source']} plays unbroken under the picture."]
    lines += ["", "EDL:", "```json", json.dumps(edl, ensure_ascii=False, indent=1), "```"]
    return "\n".join(lines)


def save_reference(project: Project, run_n: int, prepared: Prepared, *, root: Path | None = None,
                   now=time.time) -> dict:
    run = next((r for r in project.runs if r.get("n") == run_n), None)
    if run is None:
        raise BadInput(f"Không thấy lần dựng {run_n}")
    edl_file = project.dir / "runs" / str(run_n) / "edl.json"
    try:
        edl = json.loads(edl_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BadInput("Lần dựng này không có bản dựng để lưu làm mẫu")
    ref_id = reference_id(project, run_n)
    path = _path(ref_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"id": ref_id, "name": project.name or project.dir.name, "niche": project.niche,
            "project": str(project.dir), "run": run_n, "saved_at": round(now(), 3)}
    atomic_write_text(path, "---\n" + json.dumps(meta, ensure_ascii=False) + "\n---\n"
                      + build_reference(project, run, edl, prepared) + "\n")

    def mark(data: dict) -> None:
        for r in data.get("runs") or []:
            if r.get("n") == run_n:
                r["reference"] = ref_id
    update_project(project.dir, mark)
    return meta


def _read(path: Path) -> tuple[dict, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
        m = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, flags=re.S)
        meta = json.loads(m.group(1)) if m else None
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict) or not m:
        return None
    meta["id"] = path.stem
    return meta, m.group(2).strip()


def list_references(root: Path | None = None) -> list[dict]:
    """Saved references, newest first (metadata only)."""
    d = root or refs_dir()
    found = [r[0] for p in d.glob("*.md") if (r := _read(p))] if d.is_dir() else []
    return sorted(found, key=lambda m: -float(m.get("saved_at") or 0))


def delete_reference(ref_id: str, root: Path | None = None) -> None:
    path = _path(ref_id, root)
    got = _read(path)
    path.unlink(missing_ok=True)
    project = Path(got[0].get("project") or "") if got else None
    if project and (project / "project.json").is_file():
        def unmark(data: dict) -> None:
            for r in data.get("runs") or []:
                if r.get("reference") == ref_id:
                    r.pop("reference", None)
        try:
            update_project(project, unmark)
        except (OSError, ValueError, BadInput):
            pass        # the reference is gone; a stale mark in a broken project is harmless


def saved_references_text(niche: str, root: Path | None = None, exclude_project: Path | None = None) -> str:
    """The newest saved references for a prompt (same niche first); "" when there are none.
    exclude_project: a re-edit of a saved project should not be told to copy itself."""
    metas = [m for m in list_references(root)
             if not (exclude_project and Path(m.get("project") or "") == Path(exclude_project))]
    metas.sort(key=lambda m: m.get("niche") != niche)       # stable: newest first within each group
    parts = []
    for m in metas[:MAX_IN_PROMPT]:
        got = _read(_path(m["id"], root))
        if got:
            body = got[1]
            parts.append(body if len(body) <= MAX_CHARS else body[:MAX_CHARS] + "\n…(cắt bớt)")
    return "\n\n".join(parts)


def reference_text(agent_dir: Path, niche: str, project_dir: Path | None = None, root: Path | None = None) -> str:
    """Built-in video mẫu (reference-edits skill) plus the customer's saved ones."""
    from autoedit.agent.library import skill_body
    saved = saved_references_text(niche, root, exclude_project=project_dir)
    return skill_body("reference-edits", agent_dir) + (
        "\n\n# Mẫu khách đã lưu (newest first; copy their structure when the clips have the same shape)\n\n" + saved
        if saved else "")
