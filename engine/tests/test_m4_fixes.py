"""Review fixes: lost updates, routine lock, post date after upload, TikTok privacy, DST slots."""
import io
import json
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from social_fake import FakeBundle
from test_routine import R1930, fake_routes, make_root
from test_social_commands import NOW, TZ, emitter, proj, routes  # noqa: F401

from autoedit import cli
from autoedit.errors import BadInput
from autoedit.events import Emitter
from autoedit.project import LockBusy, Project, file_lock, update_project
from autoedit.social import commands, routine


def env(monkeypatch, f):
    monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k"); monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)


# -- #2 lost update ----------------------------------------------------------
def test_update_project_keeps_unknown_and_concurrent_fields(proj):
    stale = Project.load(proj)
    update_project(proj, lambda d: d.setdefault("posts", []).append({"id": "p"}))
    update_project(proj, lambda d: d["runs"].append({"n": 2}))
    data = json.loads((proj / "project.json").read_text())
    assert data["posts"] == [{"id": "p"}] and [r["n"] for r in data["runs"]] == [1, 2]
    assert stale.posts == []


def test_update_project_serialises_threads(proj):
    def add(i):
        update_project(proj, lambda d: d.setdefault("posts", []).append({"id": i}))
    ts = [threading.Thread(target=add, args=(i,)) for i in range(12)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(json.loads((proj / "project.json").read_text())["posts"]) == 12


def test_file_lock_non_blocking(tmp_path):
    lock = tmp_path / "x.lock"
    with file_lock(lock, blocking=False):
        with pytest.raises(LockBusy):
            with file_lock(lock, blocking=False):
                pass
    with file_lock(lock, blocking=False):
        pass


def test_publish_does_not_clobber_run_added_during_upload(monkeypatch, proj):
    def slow_upload(req):
        update_project(proj, lambda d: d["runs"].append({"n": 2, "summary": []}))   # an edit finishes meanwhile
        return 200, {"id": "up1"}
    r = routes(); r[("POST", "/api/v1/upload/")] = slow_upload
    with FakeBundle(r) as f:
        env(monkeypatch, f)
        commands.publish(emitter()[0], proj, 1, "t1", ["INSTAGRAM"], "hi", "now", now=NOW)
    data = json.loads((proj / "project.json").read_text())
    assert [r["n"] for r in data["runs"]] == [1, 2] and data["posts"][0]["id"] == "p1"


# -- #3 routine lock / re-check ---------------------------------------------
async def test_routine_sync_skips_when_lock_held(tmp_path, monkeypatch):
    root = make_root(tmp_path, ["a"])
    monkeypatch.setenv("AUTOEDIT_PROJECTS_ROOT", str(root))
    monkeypatch.setenv("AUTOEDIT_ROUTINES", json.dumps([R1930]))
    monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k")
    buf = io.StringIO()
    with FakeBundle(fake_routes()) as f:
        env(monkeypatch, f)
        with file_lock(root / ".routine-sync.lock", blocking=False):
            await commands.routine_sync(Emitter(buf), "t1", now=NOW)
        assert f.requests == []
    assert json.loads(buf.getvalue()) == {"type": "routine_sync", "created": [], "skipped": "Routine đang chạy"}
    buf2 = io.StringIO()      # released: the next sync runs
    with FakeBundle(fake_routes()) as f:
        env(monkeypatch, f)
        await commands.routine_sync(Emitter(buf2), "t1", now=NOW)
    assert len(json.loads(buf2.getvalue())["created"]) == 1


async def test_routine_sync_rechecks_project_before_creating(tmp_path, monkeypatch):
    root = make_root(tmp_path, ["a", "b"])
    monkeypatch.setenv("AUTOEDIT_PROJECTS_ROOT", str(root))
    monkeypatch.setenv("AUTOEDIT_ROUTINES", json.dumps([R1930]))
    monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k")

    def upload(req):    # while "b" uploads, someone publishes "a" by hand
        update_project(root / "a", lambda d: d.setdefault("posts", []).append({"id": "manual"}))
        return 200, {"id": "up"}
    r = fake_routes(); r[("POST", "/api/v1/upload/")] = upload
    with FakeBundle(r) as f:
        env(monkeypatch, f)
        await commands.routine_sync(Emitter(io.StringIO()), "t1", now=NOW)
        refs = [x.json()["referenceKey"] for x in f.calls("POST", "/api/v1/post/")]
    assert refs == ["autoedit:b:1"]      # a was posted meanwhile: no second post for it
    assert [p["id"] for p in json.loads((root / "a" / "project.json").read_text())["posts"]] == ["manual"]


# -- #4 post date after the upload ------------------------------------------
class Clock:
    def __init__(self, *times):
        self.times = list(times)

    def __call__(self, now=None):
        return self.times.pop(0) if len(self.times) > 1 else self.times[0]


def test_now_post_date_uses_clock_after_upload(monkeypatch, proj):
    monkeypatch.setattr(commands, "_now", Clock(NOW + timedelta(minutes=14)))
    with FakeBundle(routes()) as f:
        env(monkeypatch, f)
        commands.publish(emitter()[0], proj, 1, "t1", ["INSTAGRAM"], "hi", "now")
        assert f.calls("POST", "/api/v1/post/")[0].json()["postDate"] == "2026-11-20T10:15:00+07:00"


def test_picked_time_passed_during_upload_is_bad_input(monkeypatch, proj):
    monkeypatch.setattr(commands, "_now", Clock(NOW, NOW + timedelta(minutes=20)))
    with FakeBundle(routes()) as f:
        env(monkeypatch, f)
        with pytest.raises(BadInput, match="Giờ đăng đã qua"):
            commands.publish(emitter()[0], proj, 1, "t1", ["INSTAGRAM"], "hi", "2026-11-20T10:10:00+07:00")
        assert f.calls("POST", "/api/v1/post/") == []


async def test_routine_skips_slot_gone_past_and_uses_fresh_now(tmp_path, monkeypatch):
    root = make_root(tmp_path, ["a", "b"])
    monkeypatch.setenv("AUTOEDIT_PROJECTS_ROOT", str(root))
    monkeypatch.setenv("AUTOEDIT_ROUTINES", json.dumps([R1930]))
    monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k")
    # plan at 19:00; by the time the first item is reached it is 19:40, the 19:30 slot is gone; day 2 is fine
    late = NOW.replace(hour=19, minute=40)
    calls = iter([NOW.replace(hour=19, minute=0), late])
    monkeypatch.setattr(commands, "_now", lambda now=None: next(calls, late))
    buf = io.StringIO()
    with FakeBundle(fake_routes()) as f:
        env(monkeypatch, f)
        await commands.routine_sync(Emitter(buf), "t1")
        bodies = [x.json() for x in f.calls("POST", "/api/v1/post/")]
    assert [b["referenceKey"] for b in bodies] == ["autoedit:a:1"]
    assert bodies[0]["postDate"] == "2026-11-21T19:30:00+07:00"


# -- #13 privacy -------------------------------------------------------------
def tiktok_privacy_for(monkeypatch, proj, settings):
    r = routes(); r[("GET", "/api/v1/misc/tiktok/post-settings")] = settings
    with FakeBundle(r) as f:
        env(monkeypatch, f)
        commands.publish(emitter()[0], proj, 1, "t1", ["TIKTOK"], "hi", "now", now=NOW)
        assert f.calls("GET", "/api/v1/misc/tiktok/post-settings")[0].query == {"teamId": "t1"}
        return f.calls("POST", "/api/v1/post/")[0].json()["data"]["TIKTOK"]["privacy"]


def test_tiktok_privacy_public_when_allowed(monkeypatch, proj):
    assert tiktok_privacy_for(monkeypatch, proj, (200, {"privacyLevelOptions": ["SELF_ONLY", "PUBLIC_TO_EVERYONE"]})) \
        == "PUBLIC_TO_EVERYONE"


def test_tiktok_privacy_first_allowed_for_private_account(monkeypatch, proj):
    assert tiktok_privacy_for(monkeypatch, proj, (200, {"privacyLevelOptions": ["SELF_ONLY"]})) == "SELF_ONLY"


@pytest.mark.parametrize("settings", [(500, {"message": "x"}), (403, {}), (200, {})])
def test_tiktok_privacy_falls_back_to_public(monkeypatch, proj, settings):
    assert tiktok_privacy_for(monkeypatch, proj, settings) == "PUBLIC_TO_EVERYONE"


def test_no_tiktok_no_settings_call(monkeypatch, proj):
    with FakeBundle(routes()) as f:
        env(monkeypatch, f)
        commands.publish(emitter()[0], proj, 1, "t1", ["INSTAGRAM"], "hi", "now", now=NOW)
        assert f.calls("GET", "/api/v1/misc/tiktok/post-settings") == []


# -- #15 DST -----------------------------------------------------------------
def test_slots_keep_wall_clock_across_dst(monkeypatch):
    import time as t
    monkeypatch.setenv("TZ", "America/New_York"); t.tzset()
    now = datetime(2026, 10, 30, 10, 0).astimezone()      # DST ends Sun 2026-11-01
    got = routine.slots(now, [R1930])
    assert [d.strftime("%m-%d %H:%M") for d, _ in got][:4] == ["10-30 19:30", "10-31 19:30", "11-01 19:30", "11-02 19:30"]
    assert got[0][0].utcoffset() == timedelta(hours=-4) and got[3][0].utcoffset() == timedelta(hours=-5)
