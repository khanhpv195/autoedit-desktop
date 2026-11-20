import inspect

import pytest
from social_fake import FakeBundle

from autoedit.errors import SocialAuth, SocialFailed, SocialLimit
from autoedit.social import client as client_mod
from autoedit.social import posts
from autoedit.social.client import Client


def make(fake):
    return Client(key="k-123", base=fake.url)


def test_sends_api_key_header():
    with FakeBundle({("GET", "/api/v1/organization/"): (200, {"id": "o"})}) as f:
        assert make(f).organization() == {"id": "o"}
        assert f.requests[0].headers["x-api-key"] == "k-123"


def test_missing_key(monkeypatch):
    monkeypatch.delenv("BUNDLE_SOCIAL_KEY", raising=False)
    with pytest.raises(SocialAuth, match="Chưa nhập key"):
        Client()


def test_env_defaults(monkeypatch):
    with FakeBundle({("GET", "/api/v1/organization/usage/posts"): (200, {"used": 1})}) as f:
        monkeypatch.setenv("BUNDLE_SOCIAL_KEY", "envkey")
        monkeypatch.setenv("BUNDLE_SOCIAL_BASE", f.url)
        assert Client().usage_posts() == {"used": 1}
        assert f.requests[0].headers["x-api-key"] == "envkey"


@pytest.mark.parametrize("status", [401, 403])
def test_auth_error(status):
    with FakeBundle({("GET", "/api/v1/organization/"): (status, {"message": "nope"})}) as f:
        with pytest.raises(SocialAuth, match="không đúng"):
            make(f).organization()


def test_limit_error():
    with FakeBundle({("GET", "/api/v1/organization/"): (429, {})}) as f:
        with pytest.raises(SocialLimit):
            make(f).organization()


def test_failed_with_message():
    with FakeBundle({("GET", "/api/v1/organization/"): (500, {"message": "boom"})}) as f:
        with pytest.raises(SocialFailed, match="boom"):
            make(f).organization()


def test_unreachable():
    with FakeBundle() as f:
        url = f.url
    with pytest.raises(SocialFailed):
        Client(key="k", base=url).organization()


def test_teams_two_pages(monkeypatch):
    def route(req):
        off = int(req.query["offset"])
        assert req.query["limit"] == "50"
        items = [{"id": f"t{i}"} for i in range(off, min(off + 50, 60))]
        return 200, {"items": items, "total": 60}
    with FakeBundle({("GET", "/api/v1/team/"): route}) as f:
        assert len(make(f).teams()) == 60
        assert len(f.requests) == 2


def test_portal_link_body():
    with FakeBundle({("POST", "/api/v1/social-account/create-portal-link"): (200, {"url": "https://x/p"})}) as f:
        assert make(f).portal_link("T", ["TIKTOK"]) == "https://x/p"
        assert f.requests[0].json() == {"teamId": "T", "socialAccountTypes": ["TIKTOK"], "language": "en"}


def test_small_upload_multipart(tmp_path):
    video = tmp_path / "final.mp4"
    video.write_bytes(b"\x00" * (1024 * 1024))
    seen = []
    with FakeBundle({("POST", "/api/v1/upload/"): (200, {"id": "up1"})}) as f:
        assert make(f).upload("T", video, seen.append) == "up1"
        r = f.requests[0]
        assert r.headers["content-type"].startswith("multipart/form-data; boundary=")
        assert b'name="teamId"' in r.body and b'filename="final.mp4"' in r.body
        assert b"Content-Type: video/mp4" in r.body
        assert len(r.body) > 1024 * 1024
        assert r.headers["x-api-key"] == "k-123"
    assert seen and seen[-1] == pytest.approx(1.0)


def test_large_upload_init_put_finalize(tmp_path, monkeypatch):
    monkeypatch.setattr(client_mod, "LARGE", 1000)
    video = tmp_path / "big.mp4"
    video.write_bytes(b"\x01" * 5000)
    with FakeBundle() as f:
        routes = f.routes
        routes[("POST", "/api/v1/upload/init")] = (200, {"url": f.url + "/signed/abc", "path": "p/abc.mp4"})
        routes[("PUT", "/signed/abc")] = (200, None)
        routes[("POST", "/api/v1/upload/finalize")] = (200, {"id": "up9"})
        assert make(f).upload("T", video) == "up9"
        paths = [(r.method, r.path) for r in f.requests]
        assert paths == [("POST", "/api/v1/upload/init"), ("PUT", "/signed/abc"), ("POST", "/api/v1/upload/finalize")]
        assert f.requests[0].json() == {"teamId": "T", "fileName": "big.mp4", "mimeType": "video/mp4", "fileSize": 5000}
        assert "x-api-key" not in f.requests[1].headers
        assert f.requests[1].body == b"\x01" * 5000
        assert f.requests[2].json() == {"teamId": "T", "path": "p/abc.mp4"}


def test_list_posts_query():
    def route(req):
        return 200, {"items": [{"id": "p1"}], "total": 1}
    with FakeBundle({("GET", "/api/v1/post/"): route}) as f:
        assert make(f).list_posts("T", "2026-11-20T00:00:00+07:00", "2026-11-27T00:00:00+07:00") == [{"id": "p1"}]
        q = f.requests[0].query
        assert q["teamId"] == "T" and q["postDateFrom"].startswith("2026-11-20") and q["postDateTo"].startswith("2026-11-27")


def test_retry_and_get_routes():
    with FakeBundle({("POST", "/api/v1/post/p1/retry"): (200, {"id": "p1"}),
                     ("GET", "/api/v1/post/p1"): (200, {"id": "p1"})}) as f:
        c = make(f)
        assert c.retry_post("p1")["id"] == "p1" and c.get_post("p1")["id"] == "p1"


def test_no_destructive_calls():
    src = inspect.getsource(client_mod).lower()
    assert "delete" not in src
    assert '"delete"' not in src and "disconnect" not in src


def test_reference_roundtrip(tmp_path):
    key = posts.reference_key(tmp_path / "ao-so-mi", 3)
    assert key == "autoedit:ao-so-mi:3"
    assert posts.parse_reference(key) == ("ao-so-mi", 3)
    assert posts.parse_reference("autoedit:a:b:7") == ("a:b", 7)
    assert posts.parse_reference("other:x:1") is None and posts.parse_reference(None) is None
    assert posts.parse_reference("autoedit:x:y") is None


def test_normalize():
    n = posts.normalize({"id": "p", "title": "T", "status": "ERROR", "postDate": "2026-11-20T12:00:00Z",
                         "referenceKey": "autoedit:proj:2", "socialAccountTypes": ["TIKTOK", "YOUTUBE"],
                         "errors": {"TIKTOK": "token hết hạn"},
                         "externalData": {"YOUTUBE": {"permalink": "https://y/1"}, "TIKTOK": {}}})
    assert n == {"id": "p", "title": "T", "status": "ERROR", "postDate": "2026-11-20T12:00:00Z",
                 "channels": ["TIKTOK", "YOUTUBE"], "error": "TIKTOK: token hết hạn", "project": "proj", "run": 2,
                 "permalinks": {"YOUTUBE": "https://y/1"}}


def test_normalize_minimal():
    n = posts.normalize({"id": "p", "status": "SCHEDULED", "postDate": "x", "data": {"TIKTOK": {}}})
    assert n["channels"] == ["TIKTOK"] and n["error"] is None and n["project"] is None and n["run"] is None
