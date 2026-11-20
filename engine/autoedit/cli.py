import argparse
import asyncio
import json
import shutil
import sys
import traceback
from pathlib import Path

from autoedit import __version__
from autoedit.agent.analyze import run_analyze
from autoedit.agent.auth import auth_check
from autoedit.agent.options import edit_options, model
from autoedit.agent.prompt import build_edit_message
from autoedit.agent.runner import run_agent
from autoedit.agent.session import EditSession
from autoedit.agent.tools import build_server
from autoedit.claude_cli import find_cli, install_cli
from autoedit.errors import AutoeditError, NoAuth, RateLimited
from autoedit.events import Emitter
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


async def _edit(args, events: Emitter) -> int:
    find_cli()  # fail fast with SETUP_REQUIRED, before transcribing
    project = Project.load(Path(args.project))
    prepared = prepare(project, events)
    user_prompt = args.prompt if args.prompt is not None else project.prompt
    previous = _previous_edl(project) if args.feedback else None
    run_dir = project.new_run_dir()
    with open(run_dir / "agent.jsonl", "a", encoding="utf-8") as log:
        ev = Emitter(Tee(events.stream, log))
        session = EditSession(prepared=prepared, project=project, events=ev)
        usage = {"turns": 0, "fallback": False}
        ev.step("AI đang dựng…", 0.3)
        try:
            outcome = await run_agent(session, build_edit_message(project, prepared, user_prompt, args.feedback, previous,
                                                                agent_dir()),
                                      edit_options(agent_dir(), build_server(session), model()))
            usage["turns"] = outcome.turns
            ok = outcome.finished
        except (RateLimited, NoAuth):
            log.close()
            shutil.rmtree(run_dir, ignore_errors=True)
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
        res = render(prepared, project, edl, run_dir / "final.mp4", preview=False)
        (run_dir / "edl.json").write_text(json.dumps(edl.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        project.prompt = user_prompt
        project.runs.append({"n": int(run_dir.name), "final": f"runs/{run_dir.name}/final.mp4",
                             "prompt": user_prompt, "feedback": args.feedback, "summary": summary,
                             "needs_review": res.needs_review, "fallback": usage["fallback"]})
        project.save()
        ev.done(str(res.path), summary, usage, res.needs_review)
    return 0


async def _analyze(args, events: Emitter) -> int:
    find_cli()
    project = Project.load(Path(args.project))
    prepared = prepare(project, events)
    events.step("AI đang gợi ý kịch bản…", 0.6)
    events.cards(await run_analyze(prepared, project.niche, agent_dir(), args.exclude or []))
    return 0


async def _setup(args, events: Emitter) -> int:
    events.setup(str(install_cli(events)))
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
    args = p.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    events = Emitter()
    handler = {"analyze": _analyze, "edit": _edit, "auth-check": _auth, "setup": _setup}.get(args.cmd)
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
