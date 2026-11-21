import io
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from social_fake import FakeBundle

from autoedit import cli
from autoedit.errors import RateLimited
from autoedit.events import Emitter
from autoedit.social import commands, posts, routine

TZ = timezone(timedelta(hours=7))
NOW = datetime(2026, 11, 20, 10, 0, tzinfo=TZ)
R1930 = {"id": "r1", "time": "19:30", "channels": ["TIKTOK"], "enabled": True}


def test_slots_seven_days():
    s = routine.slots(NOW, [R1930])
    assert len(s) == 7
    assert s[0][0] == datetime(2026, 11, 20, 19, 30, tzinfo=TZ) and s[-1][0] == datetime(2026, 11, 26, 19, 30, tzinfo=TZ)


def test_slots_disabled_and_past_today():
    assert routine.slots(NOW, [{**R1930, "enabled": False}]) == []
    late = datetime(2026, 11, 20, 20, 0, tzinfo=TZ)
    assert routine.slots(late, [R1930])[0][0].day == 21
    two = routine.slots(NOW, [R1930, {"id": "r2", "time": "08:00", "channels": ["YOUTUBE"], "enabled": True}])
    assert [d.strftime("%d %H:%M") for d, _ in two[:3]] == ["20 19:30", "21 08:00", "21 19:30"]


def vids():
    return [{"project": "a", "run": 1, "created": "2026-11-18T10:00:00+07:00"},
            {"project": "b", "run": 1, "created": "2026-11-19T10:00:00+07:00"},
            {"project": "b", "run": 2, "created": "2026-11-19T12:00:00+07:00"},
            {"project": "c", "run": 1, "created": "2026-11-17T10:00:00+07:00"}]


def test_plan_newest_first_latest_run():
    p = routine.plan(NOW, [R1930], vids(), [])
    assert [(x["project"], x["run"]) for x in p] == [("b", 2), ("a", 1), ("c", 1)]
    assert p[0]["slot"] == "2026-11-20T19:30:00+07:00" and p[0]["channels"] == ["TIKTOK"]


def test_plan_skips_posted_and_existing_reference():
    v = vids()
    v[0]["posted"] = True
    p = routine.plan(NOW, [R1930], v, [{"referenceKey": "autoedit:c:1", "postDate": "2026-11-25T10:00:00+07:00"}])
    assert [x["project"] for x in p] == ["b"]


def test_plan_skips_slot_with_autoedit_post():
    existing = [{"referenceKey": "autoedit:zzz:1", "postDate": "2026-11-20T12:30:30Z"}]   # 19:30:30 +07
    p = routine.plan(NOW, [R1930], vids()[:1], existing)
    assert p[0]["slot"] == "2026-11-21T19:30:00+07:00"
    other = [{"referenceKey": "manual", "postDate": "2026-11-20T12:30:00Z"}]
    assert routine.plan(NOW, [R1930], vids()[:1], other)[0]["slot"] == "2026-11-20T19:30:00+07:00"


def test_plan_no_videos():
    assert routine.plan(NOW, [R1930], [], []) == []


def test_next_queue_slot():
    assert posts.next_queue_slot(NOW, [], []) == datetime(2026, 11, 21, 19, 30, tzinfo=TZ)
    assert posts.next_queue_slot(NOW, [], ["2026-11-21T19:30:00+07:00"]) == datetime(2026, 11, 22, 19, 30, tzinfo=TZ)
    assert posts.next_queue_slot(NOW, [R1930], ["2026-11-20T12:30:00Z"]) == datetime(2026, 11, 21, 19, 30, tzinfo=TZ)
    assert posts.next_queue_slot(NOW, [R1930], []) == datetime(2026, 11, 20, 19, 30, tzinfo=TZ)


def make_root(tmp_path, names):
    root = tmp_path / "projects"
    for i, n in enumerate(names):
        d = root / n
        (d / "input").mkdir(parents=True); (d / "input" / "clip.mp4").write_bytes(b"x")
        (d / "runs" / "1").mkdir(parents=True); (d / "runs" / "1" / "final.mp4").write_bytes(b"\x00" * 100)
        os.utime(d / "runs" / "1" / "final.mp4", (1_700_000_000 + i * 100,) * 2)
        (d / "project.json").write_text(json.dumps({"niche": "my-pham", "clips": ["clip.mp4"], "runs": [{"n": 1, "summary": []}]}))
        (d / "runs" / "1" / "edl.json").write_text(json.dumps({"hook": {"text": f"HOOK {n}"}}))
    return root


def fake_routes():
    return {("GET", "/api/v1/post/"): (200, {"items": [], "total": 0}),
            ("POST", "/api/v1/upload/"): (200, {"id": "up"}),
            ("POST", "/api/v1/post/"): lambda req: (200, {**req.json(), "id": "p-" + req.json()["referenceKey"], "status": "SCHEDULED"})}


async def test_routine_sync_creates_posts_with_fallback_caption(tmp_path, monkeypatch):
    root = make_root(tmp_path, ["a", "b", "c"])
    (root / "c" / "project.json").write_text(json.dumps({"niche": "my-pham", "clips": ["clip.mp4"], "runs": [{"n": 1}],
                                                         "posts": [{"id": "old"}]}))
    monkeypatch.setenv("AUTOEDIT_PROJECTS_ROOT", str(root))
    monkeypatch.setenv("AUTOEDIT_ROUTINES", json.dumps([R1930]))
    monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k")

    async def q(prompt, options):
        raise RateLimited("hết lượt")
        yield
    buf = io.StringIO()
    with FakeBundle(fake_routes()) as f:
        monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)
        await commands.routine_sync(Emitter(buf), "t1", now=NOW, query_fn=q)
        bodies = [r.json() for r in f.calls("POST", "/api/v1/post/")]
    ev = json.loads(buf.getvalue().splitlines()[-1])
    assert ev["type"] == "routine_sync" and ev["skipped"] is None and len(ev["created"]) == 2
    assert [b["referenceKey"] for b in bodies] == ["autoedit:b:1", "autoedit:a:1"]   # b is newer
    assert bodies[0]["postDate"] == "2026-11-20T19:30:00+07:00" and bodies[1]["postDate"] == "2026-11-21T19:30:00+07:00"
    assert bodies[0]["data"]["TIKTOK"]["text"] == "HOOK b\n#mypham #skincare"
    assert json.loads((root / "a" / "project.json").read_text())["posts"][0]["run"] == 1


async def test_routine_sync_uses_ai_caption(tmp_path, monkeypatch):
    from claude_agent_sdk import ResultMessage
    root = make_root(tmp_path, ["a"])
    monkeypatch.setenv("AUTOEDIT_PROJECTS_ROOT", str(root))
    monkeypatch.setenv("AUTOEDIT_ROUTINES", json.dumps([R1930]))
    monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k")

    async def q(prompt, options):
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                            session_id="s", result="Caption AI #a")
    with FakeBundle(fake_routes()) as f:
        monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)
        await commands.routine_sync(Emitter(io.StringIO()), "t1", now=NOW, query_fn=q)
        assert f.calls("POST", "/api/v1/post/")[0].json()["data"]["TIKTOK"]["text"] == "Caption AI #a"


async def test_routine_sync_no_routine(monkeypatch):
    monkeypatch.setenv("AUTOEDIT_ROUTINES", json.dumps([{**R1930, "enabled": False}]))
    monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k")
    buf = io.StringIO()
    await commands.routine_sync(Emitter(buf), "t1", now=NOW)
    assert json.loads(buf.getvalue()) == {"type": "routine_sync", "created": [], "skipped": "Chưa bật routine"}


def test_cli_routine_sync_no_routine(monkeypatch, capsys):
    monkeypatch.delenv("AUTOEDIT_ROUTINES", raising=False)
    monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k")
    assert cli.main(["social", "routine-sync", "--team", "t1"]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["skipped"] == "Chưa bật routine"


def test_publish_queue_uses_taken_slots(tmp_path, monkeypatch):
    root = make_root(tmp_path, ["a"])
    monkeypatch.setenv("AUTOEDIT_ROUTINES", json.dumps([R1930]))
    monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k")
    r = fake_routes()
    r[("GET", "/api/v1/post/")] = (200, {"items": [{"postDate": "2026-11-20T12:30:00Z"}], "total": 1})
    with FakeBundle(r) as f:
        monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)
        commands.publish(Emitter(io.StringIO()), root / "a", 1, "t1", ["TIKTOK"], "x", "queue", now=NOW)
        assert f.calls("POST", "/api/v1/post/")[0].json()["postDate"] == "2026-11-21T19:30:00+07:00"
