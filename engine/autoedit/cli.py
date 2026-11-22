import argparse
import asyncio
import contextlib
import json
import shutil
import sys
import traceback
from pathlib import Path

from autoedit import __version__
from autoedit.agent.analyze import run_analyze
from autoedit.agent.auth import auth_check
from autoedit.agent.chat import run_chat_turn
from autoedit.agent.log import serialize_message
from autoedit.agent.options import edit_options, model
from autoedit.agent.prompt import build_edit_message
from autoedit.agent.runner import run_agent
from autoedit.agent.session import EditSession
from autoedit.agent.tools import VOICE_CALL_CHARS, build_server
from autoedit.claude_cli import find_cli, install_cli
from autoedit.errors import AgentFailed, AutoeditError, NoAuth, RateLimited, VoiceError, VoiceQuota
from autoedit.events import Emitter
from autoedit import mcp_user, secrets_env
from autoedit.model_dl import install_model
from autoedit.fsutil import atomic_write_text
from autoedit.fallback import FALLBACK_SUMMARY, silence_cut_edl
from autoedit.prep import prepare
from autoedit.project import Project, update_project
from autoedit.render.pipeline import render
from autoedit.render.thumb import THUMB_NAME, backfill, make_thumb
from autoedit.resources import agent_dir
from autoedit.voice import eleven


VOICE_AGENT_FAILED = "AI chưa dựng xong bản lồng tiếng lần này, hãy thử lại"


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s: str) -> None:
        for st in self.streams:
            st.write(s)

    def flush(self) -> None:
        for st in self.streams:
            st.flush()


def _previous_edl(project: Project) -> dict | None:
    for run in reversed(project.runs):
        f = project.dir / "runs" / str(run["n"]) / "edl.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    return None


def _render_with_retry(prepared, project, edl, summary, run_dir, ev, usage):
    """Render the agent's EDL; if that fails, try once with the silence-cut EDL. Returns (result, edl, summary)."""
    try:
        return render(prepared, project, edl, run_dir / "final.mp4", preview=False), edl, summary
    except Exception:
        if usage["fallback"] or project.voiceover_on:     # never fall back to a video without the voiceover
            raise
        traceback.print_exc(file=sys.stderr)
    usage["fallback"] = True
    fb = silence_cut_edl(prepared.words, prepared.info.duration)
    ev.step("Đang xuất video…", 0.92)
    return render(prepared, project, fb, run_dir / "final.mp4", preview=False), fb, [FALLBACK_SUMMARY]


async def _edit(args, events: Emitter) -> int:
    find_cli()  # fail fast with SETUP_REQUIRED, before transcribing
    project = Project.load(Path(args.project))
    prepared = prepare(project, events)
    if project.voiceover_on and eleven.quota() < VOICE_CALL_CHARS:    # before any Claude turn is spent
        raise VoiceQuota(eleven.MSG_QUOTA)
    user_prompt = args.prompt if args.prompt is not None else project.prompt
    previous = _previous_edl(project) if args.feedback else None
    run_dir = project.new_run_dir()
    saved = False
    try:
        with open(run_dir / "agent.jsonl", "a", encoding="utf-8") as log, \
                open(run_dir / "run.log", "a", encoding="utf-8") as runlog:
            ev = Emitter(Tee(events.stream, log))

            def on_message(msg) -> None:
                log.write(json.dumps(serialize_message(msg), ensure_ascii=False) + "\n")
                log.flush()

            def cli_stderr(line: str) -> None:
                runlog.write(f"[claude] {line.rstrip()}\n")
                runlog.flush()

            session = EditSession(prepared=prepared, project=project, events=ev,
                                   target=project.target_range(user_prompt, args.feedback))
            usage = {"turns": 0, "fallback": False}
            ev.step("AI đang dựng…", 0.3)
            with contextlib.redirect_stderr(Tee(sys.stderr, runlog)):
                try:
                    user_mcp = mcp_user.load()
                    message = build_edit_message(project, prepared, user_prompt, args.feedback, previous, agent_dir(),
                                                 list(user_mcp))
                    with mcp_user.config_file(user_mcp) as mcp_file:    # 0600 temp file, removed right after the run
                        outcome = await run_agent(
                            session, message,
                            edit_options(agent_dir(), build_server(session), model(), cli_stderr, user_mcp, mcp_file,
                                         voiceover=project.voiceover_on),
                            on_message=on_message)
                    usage["turns"] = outcome.turns
                    if session.fatal is not None:
                        raise session.fatal
                    ok = outcome.finished
                except (RateLimited, NoAuth, VoiceError):
                    raise
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    if project.voiceover_on:    # the silence-cut fallback has no voiceover: fail with the error
                        raise
                    ok = False
                if ok:
                    edl, summary = session.edl, session.summary
                elif project.voiceover_on:
                    if session.voice_error is not None:     # e.g. VoiceLimit: the user can retry later
                        raise session.voice_error
                    raise AgentFailed(VOICE_AGENT_FAILED)
                else:
                    edl, summary = silence_cut_edl(prepared.words, prepared.info.duration), [FALLBACK_SUMMARY]
                    usage["fallback"] = True
                ev.step("Đang xuất video…", 0.9)
                res, edl, summary = _render_with_retry(prepared, project, edl, summary, run_dir, ev, usage)
                make_thumb(res.path, run_dir / THUMB_NAME)     # best effort: never fails the run
            atomic_write_text(run_dir / "edl.json", json.dumps(edl.to_dict(), ensure_ascii=False, indent=2))
            run_record = {"n": int(run_dir.name), "final": f"runs/{run_dir.name}/final.mp4",
                          "prompt": user_prompt, "feedback": args.feedback, "summary": summary,
                          "needs_review": res.needs_review, "fallback": usage["fallback"]}

            def record(data: dict) -> None:     # re-read under lock: a publish may have added posts meanwhile
                data["prompt"] = user_prompt
                data.setdefault("runs", []).append(run_record)
            update_project(project.dir, record)
            saved = True
            try:
                ev.done(str(res.path), summary, usage, res.needs_review)
            except OSError:
                pass    # the app quit (BrokenPipe); the run is already recorded and must stay
    except BaseException:
        if not saved:   # no half-recorded runs: nothing in project.json points here
            shutil.rmtree(run_dir, ignore_errors=True)
        raise
    return 0


async def _analyze(args, events: Emitter) -> int:
    find_cli()
    project = Project.load(Path(args.project))
    prepared = prepare(project, events)
    events.step("AI đang gợi ý kịch bản…", 0.6)
    events.cards(await run_analyze(prepared, project.niche, agent_dir(), args.exclude or [], project=project))
    return 0


async def _chat(args, events: Emitter) -> int:
    find_cli()
    project = Project.load(Path(args.project))
    prepared = prepare(project, events)
    events.step("AI đang trả lời…", 0.6)
    events.chat(await run_chat_turn(project, prepared, args.message or "", agent_dir()))
    return 0


async def _reference(args, events: Emitter) -> int:
    from autoedit.agent import references as refs
    c = args.ref_cmd
    if c == "save":
        project = Project.load(Path(args.project))
        prepared = prepare(project, events)
        events.step("Đang lưu video mẫu…", 0.9)
        events.emit_raw({"type": "reference", "reference": refs.save_reference(project, args.run, prepared)})
    elif c == "delete":
        refs.delete_reference(args.id)
        events.emit_raw({"type": "references", "references": refs.list_references()})
    else:
        events.emit_raw({"type": "references", "references": refs.list_references()})
    return 0


async def _social(args, events: Emitter) -> int:
    from autoedit.social import commands as sc
    c = args.social_cmd
    if c == "check":
        sc.check(events)
    elif c == "portal":
        sc.portal(events, args.team)
    elif c == "caption":
        from autoedit.social.caption import make_caption
        project = Project.load(Path(args.project), require_media=False)
        events.emit_raw({"type": "caption", "text": await make_caption(project, args.run, agent_dir())})
    elif c == "publish":
        sc.publish(events, Path(args.project), args.run, args.team, args.channel, args.caption, args.when)
    elif c == "list":
        sc.list_(events, args.team, args.from_, args.to)
    elif c == "retry":
        sc.retry(events, args.post)
    elif c == "routine-sync":
        await sc.routine_sync(events, args.team)
    return 0


async def _thumbs(args, events: Emitter) -> int:
    made = backfill(Path(args.root), lambda d: events.emit_raw({"type": "thumb", "dir": str(d)}))
    events.emit_raw({"type": "thumbs_done", "made": made})
    return 0


async def _mcp_check(args, events: Emitter) -> int:
    cfg = mcp_user.load().get(args.name)
    if cfg is None:
        raise AgentFailed(f"Không thấy MCP {args.name} trong cấu hình")
    events.emit_raw({"type": "mcp_tools", "name": args.name, "tools": await mcp_user.list_tools(args.name, cfg)})
    return 0


async def _setup(args, events: Emitter) -> int:
    events.setup(str(install_cli(events)))
    return 0


async def _setup_model(args, events: Emitter) -> int:
    events.model(str(install_model(events)))
    return 0


async def _auth(args, events: Emitter) -> int:
    events.auth(await auth_check(agent_dir()))
    return 0


def _utf8_stdio() -> None:
    """Windows pipes default to cp1252, which cannot hold Vietnamese; the app reads UTF-8 JSON lines."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    p = argparse.ArgumentParser(prog="autoedit")
    p.add_argument("--version", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("analyze"); a.add_argument("--project", required=True); a.add_argument("--exclude", action="append")
    c = sub.add_parser("chat"); c.add_argument("--project", required=True); c.add_argument("--message", default="")
    e = sub.add_parser("edit"); e.add_argument("--project", required=True); e.add_argument("--prompt"); e.add_argument("--feedback")
    sub.add_parser("auth-check")
    t = sub.add_parser("thumbs"); t.add_argument("--root", required=True)
    sub.add_parser("setup")
    sub.add_parser("setup-model")
    m = sub.add_parser("mcp-check"); m.add_argument("--name", required=True)
    rf = sub.add_parser("reference"); rs = rf.add_subparsers(dest="ref_cmd", required=True)
    x = rs.add_parser("save"); x.add_argument("--project", required=True); x.add_argument("--run", type=int, required=True)
    x = rs.add_parser("delete"); x.add_argument("--id", required=True)
    rs.add_parser("list")
    so = sub.add_parser("social"); ss = so.add_subparsers(dest="social_cmd", required=True)
    ss.add_parser("check")
    x = ss.add_parser("portal"); x.add_argument("--team", required=True)
    x = ss.add_parser("caption"); x.add_argument("--project", required=True); x.add_argument("--run", type=int, required=True)
    x = ss.add_parser("publish"); x.add_argument("--project", required=True); x.add_argument("--run", type=int, required=True)
    x.add_argument("--team", required=True); x.add_argument("--channel", action="append", required=True)
    x.add_argument("--caption", required=True); x.add_argument("--when", required=True)
    x = ss.add_parser("list"); x.add_argument("--team", required=True)
    x.add_argument("--from", dest="from_", required=True); x.add_argument("--to", required=True)
    x = ss.add_parser("routine-sync"); x.add_argument("--team", required=True)
    x = ss.add_parser("retry"); x.add_argument("--post", required=True)
    args = p.parse_args(argv)
    secrets_env.scrub()     # before any child process (Claude CLI, MCP servers, ffmpeg) can inherit them
    if args.version:
        print(__version__)
        return 0
    events = Emitter()
    handler = {"analyze": _analyze, "chat": _chat, "edit": _edit, "auth-check": _auth, "setup": _setup,
               "setup-model": _setup_model, "social": _social, "mcp-check": _mcp_check, "reference": _reference,
               "thumbs": _thumbs}.get(args.cmd)
    if handler is None:
        p.print_help(sys.stderr)
        return 1
    try:
        return asyncio.run(handler(args, events))
    except RateLimited as err:
        events.error(err.code, err.message, err.retry_at)
        return 2
    except AutoeditError as err:
        events.error(err.code, err.message)
        return 1
    except Exception as err:  # never leave the app without a terminal event
        traceback.print_exc(file=sys.stderr)
        events.error("AGENT_FAILED", str(err))
        return 1
