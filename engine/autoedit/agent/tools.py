import asyncio
import base64
import json
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from autoedit import __version__
from autoedit.agent.session import EditSession
from autoedit.edl import EdlError, VoiceLine, validate_edl, voice_key
from autoedit.errors import AutoeditError, VoiceAuth, VoiceError, VoiceMissing, VoiceQuota
from autoedit.fsutil import atomic_write_text
from autoedit.prep.keyframes import frame_at
from autoedit.render.pipeline import preview_frames, render
from autoedit.transcript import format_phrases, pack_phrases
from autoedit.voice import eleven
from autoedit.voice.lines import audio_duration

MAX_PREVIEWS = 3
MAX_EDL_ERRORS = 3
MAX_FRAMES = 6          # per view_frames call
MAX_VIEWED_FRAMES = 12  # per session: keeps the whole conversation far below the API's 100-images-per-request limit
TOOL_NAMES = ("get_transcript", "view_frames", "set_edl", "render_preview", "finish")
VOICE_TOOL = "voiceover"
VOICE_LINE_MAX = 120
VOICE_CALL_CHARS = 600
VOICE_MAX_CALLS = 3
VOICE_GAP = 0.3
FATAL_VOICE = (VoiceAuth, VoiceMissing, VoiceQuota)     # retrying cannot help: fail the run with this error


def tool_names(session: EditSession) -> tuple[str, ...]:
    return TOOL_NAMES + ((VOICE_TOOL,) if session.project.voiceover_on else ())


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
    return _text(f"Clip duration {dur:.2f}s. Times are timeline seconds (all clips joined in order).\n{body}")


async def view_frames(s: EditSession, args: dict) -> dict:
    dur = s.prepared.info.duration
    times = [min(max(0.0, float(t)), max(0.0, dur - 0.05)) for t in args.get("times", [])][:MAX_FRAMES]
    if not times:
        return _text("times must contain 1-6 source times", error=True)
    left = MAX_VIEWED_FRAMES - s.frames_viewed
    if left <= 0:
        return _text(f"view_frames limit reached ({MAX_VIEWED_FRAMES} frames per session). Decide from what you "
                     "have: set_edl, render_preview, finish.", error=True)
    times = times[:left]
    s.frames_viewed += len(times)
    out_dir = s.project.work_dir / "frames"
    content = [{"type": "text", "text": "Frames at " + ", ".join(f"{t:.2f}s" for t in times)}]
    for t in times:
        content.append(_image(await asyncio.to_thread(frame_at, s.prepared.normalized, t,
                                                      out_dir / f"view_{t:.2f}.jpg")))
    return {"content": content}


def cached_voice_lookup(s: EditSession):
    """Cache-only voice lookup for validate_edl (spec A4: a cache hit counts as generated). A hit is stored in the
    session like a tool-made line; never makes an HTTP call."""
    def lookup(at: float, text: str) -> VoiceLine | None:
        if not s.project.voice_id:
            return None
        hit = eleven.cached(text, s.project.voice_id, s.project.work_dir / "vo")
        if hit is None:
            return None
        try:
            line = VoiceLine(at, text, hit[0], audio_duration(hit[0]), hit[1])
        except VoiceError:
            return None     # unreadable file: treat as not generated
        s.voice_lines[(at, text)] = line
        return line
    return lookup


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
        edl, notes = validate_edl(raw, s.prepared.words, s.prepared.info.duration,
                                  image_names=s.prepared.image_names, default_cta=s.project.cta_text,
                                  voiceover_on=s.project.voiceover_on, voice_lines=s.voice_lines,
                                  voice_lookup=cached_voice_lookup(s) if s.project.voiceover_on else None,
                                  spans=s.prepared.spans)
    except (EdlError, KeyError, TypeError, ValueError, AttributeError) as e:
        s.edl_errors += 1
        if s.edl_errors >= MAX_EDL_ERRORS and s.edl is None:
            s.aborted = True
        return _text(f"Invalid EDL: {e}", error=True)
    s.edl = edl
    atomic_write_text(s.project.work_dir / "edl.json", json.dumps(edl.to_dict(), ensure_ascii=False, indent=2))
    d = edl.output_duration()
    lo, hi = s.project.length_range
    if not (lo * 0.8 <= d <= hi * 1.2):
        notes.append(f"Lưu ý: video dài {d:.1f}s, mục tiêu {lo:.0f}–{hi:.0f}s — hãy chỉnh lại.")
    out_map, t = [], 0.0
    for r in edl.ordered():
        out_map.append({"timeline": [round(r.start, 2), round(r.end, 2)], "output": [round(t, 2), round(t + r.duration, 2)]})
        t += r.duration
    msg = {"corrected_edl": edl.to_dict(), "notes": notes, "output_duration": round(d, 2), "output_map": out_map}
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
    text = f"Preview {s.previews}/{MAX_PREVIEWS}: {res.duration:.2f}s. Frames: start, then just after each cut."
    if res.checks:
        text += "\nKiểm tra: " + "; ".join(res.checks)
    content = [{"type": "text", "text": text}]
    return {"content": content + [_image(p) for p in frames]}


async def voiceover(s: EditSession, args: dict) -> dict:
    """Synthesize short voiceover lines (ElevenLabs, cached). Limits are checked before any API call."""
    if not s.project.voiceover_on:
        return _text("Voiceover is off for this video.", error=True)
    raw = args.get("lines") or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = []
    try:
        lines = [voice_key(x["at"], x["text"]) for x in raw]
    except (KeyError, TypeError, ValueError):
        return _text("lines must be a list of {at: number, text: string}", error=True)
    if not lines or any(not t for _, t in lines):
        return _text("lines must contain 1 or more {at, text} with non-empty text", error=True)
    if s.voice_calls >= VOICE_MAX_CALLS:
        return _text(f"voiceover limit reached ({VOICE_MAX_CALLS} calls per session). Use the lines you have.",
                     error=True)
    long = [t for _, t in lines if len(t) > VOICE_LINE_MAX]
    if long:
        return _text(f"each line must be one short sentence of at most {VOICE_LINE_MAX} characters: {long[0]!r}",
                     error=True)
    total = sum(len(t) for _, t in lines)
    if total > VOICE_CALL_CHARS:
        return _text(f"at most {VOICE_CALL_CHARS} characters per call (got {total}); keep the script short",
                     error=True)
    dur = s.prepared.info.duration
    for at, t in lines:
        if not 0 <= at < dur:
            return _text(f"line {t!r}: at {at} is outside the timeline 0-{dur:.2f}s", error=True)
        if s.edl is not None and s.edl.output_time(at) is None:
            return _text(f"line {t!r}: at {at} is not inside a kept range of the current EDL", error=True)
    s.voice_calls += 1
    cache = s.project.work_dir / "vo"
    made: list[VoiceLine] = []
    try:
        for at, t in lines:
            path, words = await asyncio.to_thread(eleven.tts, t, s.project.voice_id, cache)
            made.append(VoiceLine(at, t, path, await asyncio.to_thread(audio_duration, path), words))
    except VoiceError as e:
        if isinstance(e, FATAL_VOICE):
            s.aborted, s.fatal = True, e
            return _text(f"Voiceover failed: {e.message}. Stop now.", error=True)
        s.voice_error = e     # if the run then doesn't finish, it fails with this error's own code
        return _text(f"Voiceover failed: {e.message}. You may try again.", error=True)
    s.voice_error = None
    out, warnings = [], []
    for line in made:
        s.voice_lines[(line.at, line.text)] = line
        o = s.edl.output_time(line.at) if s.edl is not None else None
        out.append({"id": eleven.cache_key(s.project.voice_id, line.text), "at": line.at, "text": line.text,
                    "duration": round(line.duration, 2),
                    "out_start": None if o is None else round(o, 2),
                    "out_end": None if o is None else round(o + line.duration, 2)})
    if s.edl is not None:
        total_out = s.edl.output_duration()
        placed = sorted((x for x in out if x["out_start"] is not None), key=lambda x: x["out_start"])
        for a, b in zip(placed, placed[1:]):
            if b["out_start"] - a["out_end"] < VOICE_GAP:
                warnings.append(f"{a['text']!r} would overlap {b['text']!r} (gap under {VOICE_GAP}s): move one")
        for x in placed:
            if x["out_end"] > total_out + 0.05:
                warnings.append(f"{x['text']!r} runs past the video end ({total_out:.2f}s)")
    else:
        warnings.append("no EDL yet: out_start/out_end are known after set_edl")
    return _text(json.dumps({"lines": out, "warnings": warnings}, ensure_ascii=False))


async def finish(s: EditSession, args: dict) -> dict:
    if s.edl is None:
        return _text("Call set_edl first.", error=True)
    if s.project.voiceover_on and not s.edl.voiceover:
        return _text("Voiceover is on: call voiceover, then set_edl with `voiceover` lines, before finish.",
                     error=True)
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
            "text": {"type": "string"}}, "required": ["text"]},
        "caption_fixes": {"type": "array", "items": {
            "type": "object", "properties": {"at": _NUM, "wrong": {"type": "string"}, "right": {"type": "string"}},
            "required": ["at", "wrong", "right"]}},
        "emphasis": {"type": "array", "items": {
            "type": "object", "properties": {"at": _NUM, "word": {"type": "string"}}, "required": ["at", "word"]}},
        "broll": {"type": "array", "description": "picture-only inserts while the speech goes on: an image, or a "
                  "video cutaway (`shot` = timeline second where another shot starts, e.g. a silent product shot)",
                  "items": {
            "type": "object",
            "properties": {"image": {"type": "string", "description": "an image file name given in the request"},
                           "shot": {"type": "number", "description": "video cutaway: timeline second the shot starts"},
                           "at": _NUM, "dur": {"type": "number", "minimum": 1.5, "maximum": 4.0}},
            "required": ["at", "dur"]}},
        "cta_text": {"type": "string"},
        "music": {"type": "object", "properties": {"use": {"type": "boolean"}, "duck_db": _NUM}},
        "voiceover": {"type": "array", "description": "only when voiceover is on: lines made by the voiceover tool",
                      "items": {"type": "object", "properties": {"at": _NUM, "text": {"type": "string"}},
                                "required": ["at", "text"]}},
    },
    "required": ["keep"],
}

SCHEMAS = {
    "get_transcript": ("Read the transcript as phrases with source times. Optional start/end in seconds.",
                       {"type": "object", "properties": {"start": {"type": "number"}, "end": {"type": "number"}}}),
    "view_frames": ("See still frames at up to 6 timeline times (seconds); 12 frames in total per session.",
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
SCHEMAS[VOICE_TOOL] = (
    "Make AI voiceover lines (Vietnamese). lines = [{at: timeline second inside a kept range, text: one short "
    f"sentence ≤{VOICE_LINE_MAX} chars}}], ≤{VOICE_CALL_CHARS} chars per call, {VOICE_MAX_CALLS} calls per session. "
    "Returns each line's real duration and output window; then put the same {at, text} in set_edl `voiceover`.",
    {"type": "object", "properties": {"lines": {"type": "array", "minItems": 1, "items": {
        "type": "object", "properties": {"at": _NUM, "text": {"type": "string"}}, "required": ["at", "text"]}}},
     "required": ["lines"]})
HANDLERS = {"get_transcript": get_transcript, "view_frames": view_frames, "set_edl": set_edl,
            "render_preview": render_preview, "finish": finish, VOICE_TOOL: voiceover}


def build_server(session: EditSession):
    def bind(fn):
        async def handler(args):
            return await fn(session, args)
        return handler

    sdk_tools = [tool(name, SCHEMAS[name][0], SCHEMAS[name][1])(bind(HANDLERS[name])) for name in tool_names(session)]
    return create_sdk_mcp_server(name="autoedit", version=__version__, tools=sdk_tools)
