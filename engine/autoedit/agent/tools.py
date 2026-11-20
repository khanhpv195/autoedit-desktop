import asyncio
import base64
import json
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from autoedit import __version__
from autoedit.agent.session import EditSession
from autoedit.edl import EdlError, validate_edl
from autoedit.errors import AutoeditError
from autoedit.prep.keyframes import frame_at
from autoedit.render.pipeline import preview_frames, render
from autoedit.transcript import format_phrases, pack_phrases

MAX_PREVIEWS = 3
MAX_EDL_ERRORS = 3
MAX_FRAMES = 6
TOOL_NAMES = ("get_transcript", "view_frames", "set_edl", "render_preview", "finish")


def _text(t: str, error: bool = False) -> dict:
    res = {"content": [{"type": "text", "text": t}]}
    if error:
        res["is_error"] = True
    return res


def _image(p: Path) -> dict:
    return {"type": "image", "data": base64.b64encode(p.read_bytes()).decode(), "mimeType": "image/jpeg"}


async def get_transcript(s: EditSession, args: dict) -> dict:
    dur = s.prepared.info.duration
    a, b = float(args.get("start", 0.0)), float(args.get("end", dur))
    sel = [w for w in s.prepared.words if w.end > a and w.start < b]
    body = format_phrases(pack_phrases(sel)) or "(no speech in this range)"
    return _text(f"Clip duration {dur:.2f}s. Times are source seconds.\n{body}")


async def view_frames(s: EditSession, args: dict) -> dict:
    dur = s.prepared.info.duration
    times = [min(max(0.0, float(t)), max(0.0, dur - 0.05)) for t in args.get("times", [])][:MAX_FRAMES]
    if not times:
        return _text("times must contain 1-6 source times", error=True)
    out_dir = s.project.work_dir / "frames"
    content = [{"type": "text", "text": "Frames at " + ", ".join(f"{t:.2f}s" for t in times)}]
    for t in times:
        content.append(_image(await asyncio.to_thread(frame_at, s.prepared.normalized, t,
                                                      out_dir / f"view_{t:.2f}.jpg")))
    return {"content": content}


async def set_edl(s: EditSession, args: dict) -> dict:
    if s.edl_errors >= MAX_EDL_ERRORS and s.edl is None:
        s.aborted = True
        return _text("Too many invalid edits. The app will use its automatic cut; stop now.", error=True)
    try:
        raw = args.get("edl") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError as e:
                raise EdlError(f"edl is not valid JSON: {e}") from e
        edl, notes = validate_edl(raw, s.prepared.words, s.prepared.info.duration)
    except (EdlError, KeyError, TypeError, ValueError, AttributeError) as e:
        s.edl_errors += 1
        if s.edl_errors >= MAX_EDL_ERRORS and s.edl is None:
            s.aborted = True
        return _text(f"Invalid EDL: {e}", error=True)
    s.edl = edl
    (s.project.work_dir / "edl.json").write_text(json.dumps(edl.to_dict(), ensure_ascii=False, indent=2),
                                                 encoding="utf-8")
    msg = {"corrected_edl": edl.to_dict(), "notes": notes, "output_duration": round(edl.output_duration(), 2)}
    return _text(json.dumps(msg, ensure_ascii=False))


async def render_preview(s: EditSession, args: dict) -> dict:
    if s.edl is None:
        return _text("Call set_edl first.", error=True)
    if s.previews >= MAX_PREVIEWS:
        return _text("Preview limit reached. Call finish.", error=True)
    try:
        res = await asyncio.to_thread(render, s.prepared, s.project, s.edl, s.project.work_dir / "preview.mp4",
                                      preview=True)
    except AutoeditError as e:
        return _text(f"Preview failed: {e.message}", error=True)
    s.previews += 1
    s.events.preview(str(res.path), s.previews)
    frames = await asyncio.to_thread(preview_frames, res.path, s.edl, s.project.work_dir / "frames")
    content = [{"type": "text", "text": f"Preview {s.previews}/{MAX_PREVIEWS}: {res.duration:.2f}s. "
                                        "Frames: start, then just after each cut."}]
    return {"content": content + [_image(p) for p in frames]}


async def finish(s: EditSession, args: dict) -> dict:
    if s.edl is None:
        return _text("Call set_edl first.", error=True)
    summary = [str(x).strip() for x in args.get("summary", []) if str(x).strip()][:4]
    if not summary:
        return _text("summary must have 1-4 short Vietnamese bullets", error=True)
    s.summary, s.finished = summary, True
    return _text("Done. The app will render the final video.")


_NUM = {"type": "number"}
EDL_SCHEMA = {
    "type": "object",
    "properties": {
        "keep": {"type": "array", "minItems": 1, "items": {
            "type": "object", "properties": {"start": _NUM, "end": _NUM, "reason": {"type": "string"}},
            "required": ["start", "end"]}},
        "hook": {"type": ["object", "null"], "properties": {
            "move_to_front": {"type": "array", "items": _NUM, "minItems": 2, "maxItems": 2},
            "text": {"type": "string"}}, "required": ["move_to_front", "text"]},
        "caption_fixes": {"type": "array", "items": {
            "type": "object", "properties": {"at": _NUM, "wrong": {"type": "string"}, "right": {"type": "string"}},
            "required": ["at", "wrong", "right"]}},
        "emphasis": {"type": "array", "items": {
            "type": "object", "properties": {"at": _NUM, "word": {"type": "string"}}, "required": ["at", "word"]}},
        "cta_text": {"type": "string"},
        "music": {"type": "object", "properties": {"use": {"type": "boolean"}, "duck_db": _NUM}},
    },
    "required": ["keep"],
}

SCHEMAS = {
    "get_transcript": ("Read the transcript as phrases with source times. Optional start/end in seconds.",
                       {"type": "object", "properties": {"start": {"type": "number"}, "end": {"type": "number"}}}),
    "view_frames": ("See still frames at up to 6 source times (seconds).",
                    {"type": "object", "properties": {"times": {"type": "array", "items": {"type": "number"},
                                                                "minItems": 1, "maxItems": 6}},
                     "required": ["times"]}),
    "set_edl": ("Submit the edit decision list. Edges that fall inside a word snap to the word (padded); edges in "
                "silence are kept as given, so silent product shots inside a range survive. Returns the corrected "
                "EDL plus notes (dropped pieces, caption_fixes/emphasis that matched nothing) or an error to fix.",
                {"type": "object", "properties": {"edl": EDL_SCHEMA}, "required": ["edl"]}),
    "render_preview": ("Render a 540p preview of the current EDL and return frames at the start and each cut.",
                       {"type": "object", "properties": {}}),
    "finish": ("Lock the current EDL. summary = 1-4 short customer-facing Vietnamese bullets.",
               {"type": "object", "properties": {"summary": {"type": "array", "items": {"type": "string"},
                                                             "minItems": 1, "maxItems": 4}},
                "required": ["summary"]}),
}
HANDLERS = {"get_transcript": get_transcript, "view_frames": view_frames, "set_edl": set_edl,
            "render_preview": render_preview, "finish": finish}


def build_server(session: EditSession):
    def bind(fn):
        async def handler(args):
            return await fn(session, args)
        return handler

    sdk_tools = [tool(name, SCHEMAS[name][0], SCHEMAS[name][1])(bind(HANDLERS[name])) for name in TOOL_NAMES]
    return create_sdk_mcp_server(name="autoedit", version=__version__, tools=sdk_tools)
