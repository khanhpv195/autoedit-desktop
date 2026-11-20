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
from autoedit.agent.log import serialize_message
from autoedit.agent.options import edit_options, model
from autoedit.agent.prompt import build_edit_message
from autoedit.agent.runner import run_agent
from autoedit.agent.session import EditSession
from autoedit.agent.tools import build_server
from autoedit.claude_cli import find_cli, install_cli
from autoedit.errors import AutoeditError, NoAuth, RateLimited
from autoedit.events import Emitter
from autoedit.model_dl import install_model
from autoedit.fsutil import atomic_write_text
from autoedit.fallback import FALLBACK_SUMMARY, silence_cut_edl
from autoedit.prep import prepare
from autoedit.project import Project
from autoedit.render.pipeline import render
from autoedit.resources import agent_dir


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
        if usage["fallback"]:
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

            session = EditSession(prepared=prepared, project=project, events=ev)
            usage = {"turns": 0, "fallback": False}
            ev.step("AI đang dựng…", 0.3)
            with contextlib.redirect_stderr(Tee(sys.stderr, runlog)):
                try:
                    message = build_edit_message(project, prepared, user_prompt, args.feedback, previous, agent_dir())
                    outcome = await run_agent(session, message, edit_options(agent_dir(), build_server(session), model(), cli_stderr),
                                              on_message=on_message)
                    usage["turns"] = outcome.turns
                    ok = outcome.finished
                except (RateLimited, NoAuth):
                    raise
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    ok = False
                if ok:
                    edl, summary = session.edl, session.summary
                else:
                    edl, summary = silence_cut_edl(prepared.words, prepared.info.duration), [FALLBACK_SUMMARY]
                    usage["fallback"] = True
                ev.step("Đang xuất video…", 0.9)
                res, edl, summary = _render_with_retry(prepared, project, edl, summary, run_dir, ev, usage)
            atomic_write_text(run_dir / "edl.json", json.dumps(edl.to_dict(), ensure_ascii=False, indent=2))
            project.prompt = user_prompt
            project.runs.append({"n": int(run_dir.name), "final": f"runs/{run_dir.name}/final.mp4",
                                 "prompt": user_prompt, "feedback": args.feedback, "summary": summary,
                                 "needs_review": res.needs_review, "fallback": usage["fallback"]})
            project.save()
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
    events.cards(await run_analyze(prepared, project.niche, agent_dir(), args.exclude or []))
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
        project = Project.load(Path(args.project))
        events.emit_raw({"type": "caption", "text": await make_caption(project, args.run, agent_dir())})
    elif c == "publish":
        sc.publish(events, Path(args.project), args.run, args.team, args.channel, args.caption, args.when)
    elif c == "list":
        sc.list_(events, args.team, args.from_, args.to)
    elif c == "retry":
        sc.retry(events, args.post)
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="autoedit")
    p.add_argument("--version", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("analyze"); a.add_argument("--project", required=True); a.add_argument("--exclude", action="append")
    e = sub.add_parser("edit"); e.add_argument("--project", required=True); e.add_argument("--prompt"); e.add_argument("--feedback")
    sub.add_parser("auth-check")
    sub.add_parser("setup")
    sub.add_parser("setup-model")
    so = sub.add_parser("social"); ss = so.add_subparsers(dest="social_cmd", required=True)
    ss.add_parser("check")
    x = ss.add_parser("portal"); x.add_argument("--team", required=True)
    x = ss.add_parser("caption"); x.add_argument("--project", required=True); x.add_argument("--run", type=int, required=True)
    x = ss.add_parser("publish"); x.add_argument("--project", required=True); x.add_argument("--run", type=int, required=True)
    x.add_argument("--team", required=True); x.add_argument("--channel", action="append", required=True)
    x.add_argument("--caption", required=True); x.add_argument("--when", required=True)
    x = ss.add_parser("list"); x.add_argument("--team", required=True)
    x.add_argument("--from", dest="from_", required=True); x.add_argument("--to", required=True)
    x = ss.add_parser("retry"); x.add_argument("--post", required=True)
    args = p.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    events = Emitter()
    handler = {"analyze": _analyze, "edit": _edit, "auth-check": _auth, "setup": _setup,
               "setup-model": _setup_model, "social": _social}.get(args.cmd)
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
