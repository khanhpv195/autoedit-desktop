import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
from social_fake import FakeBundle

from autoedit import cli
from autoedit.errors import BadInput, NoAuth, RateLimited
from autoedit.events import Emitter
from autoedit.project import Project
from autoedit.social import commands
from autoedit.social.caption import make_caption
from autoedit.resources import agent_dir

TZ = timezone(timedelta(hours=7))
NOW = datetime(2026, 11, 20, 10, 0, tzinfo=TZ)


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "ao-dai"
    (d / "input").mkdir(parents=True)
    (d / "input" / "clip.mp4").write_bytes(b"x")
    (d / "runs" / "1").mkdir(parents=True)
    (d / "runs" / "1" / "final.mp4").write_bytes(b"\x00" * 2048)
    (d / "project.json").write_text(json.dumps({"niche": "my-pham", "clip": "clip.mp4",
                                                "runs": [{"n": 1, "summary": ["Bỏ đoạn lặng"]}]}))
    return d


def routes(**over):
    r = {("POST", "/api/v1/upload/"): (200, {"id": "up1"}),
         ("POST", "/api/v1/post/"): lambda req: (200, {**req.json(), "id": "p1", "status": "SCHEDULED"})}
    r.update(over)
    return r


def emitter():
    buf = io.StringIO()
    return Emitter(buf), lambda: [json.loads(l) for l in buf.getvalue().splitlines()]


def test_check_merges_org_usage_teams(monkeypatch):
    r = {("GET", "/api/v1/organization/"): (200, {"name": "Shop A"}),
         ("GET", "/api/v1/organization/usage/posts"): (200, {"used": 11, "limit": 20, "remaining": 9}),
         ("GET", "/api/v1/organization/usage/uploads"): (200, {"used": 1, "limit": 50, "remaining": 49}),
         ("GET", "/api/v1/team/"): (200, {"items": [{"id": "t1", "name": "Team 1"}], "total": 1}),
         ("GET", "/api/v1/team/t1"): (200, {"id": "t1", "name": "Team 1", "socialAccounts": [
             {"type": "TIKTOK", "displayName": "Shop TikTok", "username": "shopa", "avatarUrl": "http://a/1.png"}]})}
    with FakeBundle(r) as f:
        monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k"); monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)
        ev, out = emitter()
        commands.check(ev)
    assert out() == [{"type": "social_account", "organization": {"name": "Shop A"},
                      "usage": {"posts": {"used": 11, "limit": 20, "remaining": 9},
                                "uploads": {"used": 1, "limit": 50, "remaining": 49}},
                      "teams": [{"id": "t1", "name": "Team 1", "channels": [
                          {"type": "TIKTOK", "name": "Shop TikTok", "avatar": "http://a/1.png", "username": "shopa"}]}]}]


def test_portal(monkeypatch):
    with FakeBundle({("POST", "/api/v1/social-account/create-portal-link"): (200, {"url": "https://p/1"})}) as f:
        monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k"); monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)
        ev, out = emitter()
        commands.portal(ev, "t1")
        assert out() == [{"type": "social_portal", "url": "https://p/1"}]
        assert f.requests[0].json()["socialAccountTypes"] == ["TIKTOK", "INSTAGRAM", "YOUTUBE", "FACEBOOK"]


def test_publish_now_body_and_project_record(monkeypatch, proj):
    with FakeBundle(routes()) as f:
        monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k"); monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)
        ev, out = emitter()
        caption = "Son lì mới về #mypham #son"
        commands.publish(ev, proj, 1, "t1", ["TIKTOK", "YOUTUBE", "INSTAGRAM", "FACEBOOK"], caption, "now", now=NOW)
        body = f.calls("POST", "/api/v1/post/")[0].json()
    assert body["teamId"] == "t1" and body["status"] == "SCHEDULED"
    assert body["referenceKey"] == "autoedit:ao-dai:1"
    assert body["postDate"] == "2026-11-20T10:01:00+07:00"
    assert body["title"] == caption
    assert body["socialAccountTypes"] == ["TIKTOK", "YOUTUBE", "INSTAGRAM", "FACEBOOK"]
    assert body["data"] == {
        "TIKTOK": {"type": "VIDEO", "text": caption, "uploadIds": ["up1"], "privacy": "PUBLIC_TO_EVERYONE"},
        "YOUTUBE": {"type": "SHORT", "text": caption, "description": caption, "uploadIds": ["up1"]},
        "INSTAGRAM": {"type": "REEL", "text": caption, "uploadIds": ["up1"]},
        "FACEBOOK": {"type": "REEL", "text": caption, "uploadIds": ["up1"]}}
    events_out = out()
    assert events_out[-1]["type"] == "social_post" and events_out[-1]["post"]["id"] == "p1"
    assert events_out[-1]["post"]["project"] == "ao-dai" and events_out[-1]["post"]["run"] == 1
    assert any(e["type"] == "step" and "Đang tải video lên" in e["label"] for e in events_out)
    saved = json.loads((proj / "project.json").read_text())["posts"]
    assert saved == [{"id": "p1", "run": 1, "postDate": "2026-11-20T10:01:00+07:00",
                      "channels": ["TIKTOK", "YOUTUBE", "INSTAGRAM", "FACEBOOK"], "status": "SCHEDULED"}]
    assert Project.load(proj).posts == saved


def test_publish_only_selected_channels(monkeypatch, proj):
    with FakeBundle(routes()) as f:
        monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k"); monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)
        commands.publish(emitter()[0], proj, 1, "t1", ["TIKTOK"], "hi", "2026-11-21T19:30:00+07:00", now=NOW)
        body = f.calls("POST", "/api/v1/post/")[0].json()
    assert list(body["data"]) == ["TIKTOK"] and body["postDate"] == "2026-11-21T19:30:00+07:00"


@pytest.mark.parametrize("kw,msg", [
    ({"when": "2026-11-20T09:00:00+07:00"}, "Giờ đăng đã qua"),
    ({"when": "không phải giờ"}, "định dạng"),
    ({"channels": ["TWITTER"]}, "TWITTER"),
    ({"channels": []}, "kênh"),
    ({"run": 9}, "bản dựng"),
    ({"caption": "x" * 2201}, "2200"),
])
def test_publish_bad_input(monkeypatch, proj, kw, msg):
    args = dict(run=1, channels=["TIKTOK"], caption="ok", when="now")
    args.update(kw)
    with FakeBundle(routes()) as f:
        monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k"); monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)
        with pytest.raises(BadInput, match=msg):
            commands.publish(emitter()[0], proj, args["run"], "t1", args["channels"], args["caption"], args["when"], now=NOW)
        assert f.requests == []


def test_publish_no_final(monkeypatch, proj):
    (proj / "runs" / "1" / "final.mp4").unlink()
    monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k")
    with pytest.raises(BadInput, match="final.mp4"):
        commands.publish(emitter()[0], proj, 1, "t1", ["TIKTOK"], "x", "now", now=NOW)


def test_list_normalizes(monkeypatch):
    items = [{"id": "p1", "title": "a", "status": "POSTED", "postDate": "2026-11-20T12:00:00Z",
              "referenceKey": "autoedit:ao-dai:2", "socialAccountTypes": ["TIKTOK"]},
             {"id": "p2", "title": "b", "status": "DELETED", "postDate": "2026-11-20T13:00:00Z"}]
    with FakeBundle({("GET", "/api/v1/post/"): (200, {"items": items, "total": 2})}) as f:
        monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k"); monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)
        ev, out = emitter()
        commands.list_(ev, "t1", "2026-11-16T00:00:00+07:00", "2026-11-23T00:00:00+07:00")
    posts = out()[0]["posts"]
    assert out()[0]["type"] == "social_posts" and [p["id"] for p in posts] == ["p1"]
    assert posts[0]["project"] == "ao-dai" and posts[0]["run"] == 2


def test_retry(monkeypatch):
    with FakeBundle({("POST", "/api/v1/post/p7/retry"): (200, {"id": "p7", "status": "RETRYING", "postDate": "x"})}) as f:
        monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k"); monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)
        ev, out = emitter()
        commands.retry(ev, "p7")
    assert out()[0]["post"]["status"] == "RETRYING"


# -- caption ---------------------------------------------------------------
def result(text):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                         session_id="s", result=text)


async def test_caption_with_fake_query(proj):
    (proj / "work").mkdir()
    (proj / "work" / "transcript.json").write_text(json.dumps({"sha256": "x", "words": [
        {"text": "son", "start": 1.0, "end": 1.3}, {"text": "189K", "start": 1.4, "end": 2.0}]}))
    (proj / "runs" / "1" / "edl.json").write_text(json.dumps({"hook": {"text": "CHỈ 189K"}}))
    seen = {}

    async def q(prompt, options):
        seen["prompt"], seen["tools"] = prompt, options.tools
        yield result("  Son đẹp #son  ")
    text = await make_caption(Project.load(proj), 1, agent_dir(), query_fn=q)
    assert text == "Son đẹp #son"
    assert "son 189K" in seen["prompt"] and "CHỈ 189K" in seen["prompt"] and "Bỏ đoạn lặng" in seen["prompt"]
    assert "Mỹ phẩm" in seen["prompt"] and "300" in seen["prompt"]
    assert seen["tools"] == []


async def test_caption_rate_limited(proj):
    async def q(prompt, options):
        yield AssistantMessage(content=[TextBlock("x")], model="m", error="rate_limit")
    with pytest.raises(RateLimited):
        await make_caption(Project.load(proj), 1, agent_dir(), query_fn=q)


async def test_caption_no_auth(proj):
    async def q(prompt, options):
        yield AssistantMessage(content=[], model="m", error="authentication_failed")
    with pytest.raises(NoAuth):
        await make_caption(Project.load(proj), 1, agent_dir(), query_fn=q)


# -- CLI -------------------------------------------------------------------
def test_cli_check_ok(monkeypatch, capsys):
    r = {("GET", "/api/v1/organization/"): (200, {"name": "S"}),
         ("GET", "/api/v1/organization/usage/posts"): (200, {"used": 0, "limit": 5, "remaining": 5}),
         ("GET", "/api/v1/organization/usage/uploads"): (200, {"used": 0, "limit": 5, "remaining": 5}),
         ("GET", "/api/v1/team/"): (200, {"items": [], "total": 0})}
    with FakeBundle(r) as f:
        monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k"); monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)
        assert cli.main(["social", "check"]) == 0
    last = [json.loads(l) for l in capsys.readouterr().out.splitlines()][-1]
    assert last["type"] == "social_account"


def test_cli_missing_key(monkeypatch, capsys):
    monkeypatch.delenv("BUNDLE_SOCIAL_KEY", raising=False)
    assert cli.main(["social", "check"]) == 1
    last = [json.loads(l) for l in capsys.readouterr().out.splitlines()][-1]
    assert last["type"] == "error" and last["code"] == "SOCIAL_AUTH"


def test_cli_publish_past_is_bad_input(monkeypatch, capsys, proj):
    monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k")
    code = cli.main(["social", "publish", "--project", str(proj), "--run", "1", "--team", "t1", "--channel", "TIKTOK",
                     "--caption", "x", "--when", "2020-01-01T00:00:00+00:00"])
    assert code == 1
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["code"] == "BAD_INPUT"


def test_cli_publish_ok(monkeypatch, capsys, proj):
    with FakeBundle(routes()) as f:
        monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "k"); monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)
        assert cli.main(["social", "publish", "--project", str(proj), "--run", "1", "--team", "t1", "--channel", "TIKTOK",
                         "--channel", "YOUTUBE", "--caption", "#a b", "--when", "now"]) == 0
    last = [json.loads(l) for l in capsys.readouterr().out.splitlines()][-1]
    assert last["type"] == "social_post" and last["post"]["channels"] == ["TIKTOK", "YOUTUBE"]
