"""`autoedit social …` commands. Every function emits the Contract event (see the M4 plan)."""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from autoedit.errors import BadInput
from autoedit.events import Emitter
from autoedit.project import Project
from autoedit.social import posts
from autoedit.social.client import Client

V2_CHANNELS = ("TIKTOK", "INSTAGRAM", "YOUTUBE", "FACEBOOK")
MAX_CAPTION = 2200


def _client(client: Client | None) -> Client:
    return client or Client()


def _channel(acc: dict) -> dict:
    return {"type": acc.get("type"),
            "name": acc.get("displayName") or acc.get("userDisplayName") or acc.get("username") or "",
            "avatar": acc.get("avatarUrl"), "username": acc.get("username") or acc.get("userUsername")}


def _usage(u: dict) -> dict:
    return {k: u.get(k) for k in ("used", "limit", "remaining")}


def check(events: Emitter, client: Client | None = None) -> None:
    c = _client(client)
    org = c.organization()
    usage = {"posts": _usage(c.usage_posts()), "uploads": _usage(c.usage_uploads())}
    teams = []
    for t in c.teams():
        full = c.team(t["id"])
        teams.append({"id": t["id"], "name": full.get("name") or t.get("name") or "",
                      "channels": [_channel(a) for a in full.get("socialAccounts") or []]})
    events.emit_raw({"type": "social_account", "organization": {"name": org.get("name") or ""},
                     "usage": usage, "teams": teams})


def portal(events: Emitter, team: str, client: Client | None = None) -> None:
    url = _client(client).portal_link(team, list(V2_CHANNELS))
    events.emit_raw({"type": "social_portal", "url": url})


def _now(now: datetime | None) -> datetime:
    return now or datetime.now().astimezone()


def _parse_when(when: str, now: datetime) -> datetime:
    try:
        dt = datetime.fromisoformat(when)
    except ValueError:
        raise BadInput("Giờ đăng không đúng định dạng") from None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    if dt <= now:
        raise BadInput("Giờ đăng đã qua")
    return dt


def _routines() -> list[dict]:
    try:
        data = json.loads(os.environ.get("AUTOEDIT_ROUTINES") or "[]")
    except ValueError:
        print("AUTOEDIT_ROUTINES không đọc được", file=sys.stderr)
        return []
    return data if isinstance(data, list) else []


def build_body(team: str, project_dir: Path, run: int, channels: list[str], caption: str, upload_id: str,
               post_date: datetime) -> dict:
    """POST /api/v1/post/ body, per the swagger: TIKTOK type VIDEO + privacy, INSTAGRAM/FACEBOOK type REEL,
    YOUTUBE type SHORT where `text` is the title and `description` the caption."""
    base = {"text": caption, "uploadIds": [upload_id]}
    first_line = caption.strip().splitlines()[0] if caption.strip() else ""
    data = {
        "TIKTOK": {"type": "VIDEO", **base, "privacy": "PUBLIC_TO_EVERYONE"},
        "INSTAGRAM": {"type": "REEL", **base},
        "YOUTUBE": {"type": "SHORT", "text": first_line[:100], "description": caption, "uploadIds": [upload_id]},
        "FACEBOOK": {"type": "REEL", **base},
    }
    return {"teamId": team, "title": caption.strip()[:80] or "AutoEdit", "referenceKey": posts.reference_key(project_dir, run),
            "postDate": post_date.isoformat(timespec="seconds"), "status": "SCHEDULED",
            "socialAccountTypes": list(channels), "data": {c: data[c] for c in channels}}


def create_post(project_dir: Path, run: int, team: str, channels: list[str], caption: str, when: str,
                now: datetime | None = None, events: Emitter | None = None, client: Client | None = None) -> dict:
    """Validate, upload final.mp4, create the post, record it in project.json. Returns the normalized Post."""
    now = _now(now)
    project = Project.load(project_dir)
    if not any(r.get("n") == run for r in project.runs):
        raise BadInput(f"Không thấy bản dựng {run}")
    final = project.dir / "runs" / str(run) / "final.mp4"
    if not final.exists():
        raise BadInput("Chưa có video final.mp4 của bản dựng này")
    channels = list(dict.fromkeys(channels))
    if not channels:
        raise BadInput("Chưa chọn kênh đăng")
    bad = [c for c in channels if c not in V2_CHANNELS]
    if bad:
        raise BadInput("Kênh chưa hỗ trợ đăng video: " + ", ".join(bad))
    if len(caption) > MAX_CAPTION:
        raise BadInput(f"Caption dài quá {MAX_CAPTION} ký tự")
    if when == "now":
        post_date = now + timedelta(minutes=1)
    elif when == "queue":
        post_date = None
    else:
        post_date = _parse_when(when, now)
    c = _client(client)
    if post_date is None:
        taken = [p.get("postDate") for p in c.list_posts(team, now.isoformat(timespec="seconds"),
                                                           (now + timedelta(days=30)).isoformat(timespec="seconds"))]
        post_date = posts.next_queue_slot(now, _routines(), [t for t in taken if t])
    last = [-1]

    def progress(frac: float) -> None:
        pct = int(frac * 100)
        if events is not None and pct != last[0]:
            last[0] = pct
            events.step(f"Đang tải video lên… {pct}%", 0.1 + 0.8 * frac)

    if events is not None:
        events.step("Đang tải video lên… 0%", 0.1)
    upload_id = c.upload(team, final, progress)
    if events is not None:
        events.step("Đang lên lịch đăng…", 0.95)
    raw = c.create_post(build_body(team, project.dir, run, channels, caption, upload_id, post_date))
    post = posts.normalize(raw)
    project.posts.append({"id": post["id"], "run": run, "postDate": post["postDate"] or post_date.isoformat(timespec="seconds"),
                          "channels": post["channels"] or channels, "status": post["status"]})
    project.save()
    return post


def publish(events: Emitter, project_dir: Path, run: int, team: str, channels: list[str], caption: str, when: str,
            now: datetime | None = None, client: Client | None = None) -> dict:
    post = create_post(project_dir, run, team, channels, caption, when, now, events, client)
    events.emit_raw({"type": "social_post", "post": post})
    return post


def list_(events: Emitter, team: str, start: str, end: str, client: Client | None = None) -> None:
    items = [posts.normalize(p) for p in _client(client).list_posts(team, start, end)]
    events.emit_raw({"type": "social_posts", "posts": [p for p in items if p["status"] != "DELETED"]})


def retry(events: Emitter, post_id: str, client: Client | None = None) -> None:
    events.emit_raw({"type": "social_post", "post": posts.normalize(_client(client).retry_post(post_id))})


FALLBACK_TAGS = {"thoi-trang": "#thoitrang #outfit", "my-pham": "#mypham #skincare", "do-an": "#monngon #review",
                 "phu-kien": "#phukien #xuhuong", "chung": "#xuhuong #review"}


def fallback_caption(project_dir: Path, run: int, niche: str) -> str:
    from autoedit.social.caption import _hook
    hook = _hook(Project.load(project_dir), run) or "Xem ngay"
    return f"{hook}\n{FALLBACK_TAGS.get(niche, FALLBACK_TAGS['chung'])}"


def scan_videos(root: Path) -> list[dict]:
    """One entry per finished run of every project under root (`posted` = project.json has posts)."""
    out = []
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        f = d / "project.json"
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in data.get("runs") or []:
            final = d / "runs" / str(r.get("n")) / "final.mp4"
            if final.is_file():
                created = datetime.fromtimestamp(final.stat().st_mtime).astimezone().isoformat(timespec="seconds")
                out.append({"project": d.name, "run": r["n"], "created": created, "posted": bool(data.get("posts")),
                            "niche": data.get("niche")})
    return out


async def routine_sync(events: Emitter, team: str, now: datetime | None = None, client: Client | None = None,
                       query_fn=None) -> None:
    from autoedit.errors import AgentFailed, AutoeditError, NoAuth, RateLimited, SocialFailed, SocialLimit
    from autoedit.resources import agent_dir
    from autoedit.social import routine
    from autoedit.social.caption import make_caption
    kw = {"query_fn": query_fn} if query_fn else {}
    now = _now(now)
    routines = [r for r in _routines() if isinstance(r, dict)]
    if not any(r.get("enabled") for r in routines):
        events.emit_raw({"type": "routine_sync", "created": [], "skipped": "Chưa bật routine"})
        return
    root = Path(os.environ.get("AUTOEDIT_PROJECTS_ROOT") or "")
    c = _client(client)
    existing = c.list_posts(team, now.isoformat(timespec="seconds"), (now + timedelta(days=7)).isoformat(timespec="seconds"))
    niches = {v["project"]: v["niche"] for v in scan_videos(root)}
    items = routine.plan(now, routines, scan_videos(root), existing)
    created, skipped = [], None
    for it in items:
        channels = [ch for ch in it["channels"] if ch in V2_CHANNELS]
        if not channels:
            continue
        pdir = root / it["project"]
        try:
            try:
                text = await make_caption(Project.load(pdir), it["run"], agent_dir(), **kw)
            except (RateLimited, NoAuth, AgentFailed):
                text = fallback_caption(pdir, it["run"], niches.get(it["project"]) or "chung")
            created.append(create_post(pdir, it["run"], team, channels, text, it["slot"], now, None, c))
        except (SocialLimit, SocialFailed) as e:
            if not created:
                raise
            skipped = e.message
            break
        except AutoeditError as e:   # one broken project must not block the rest
            print(f"routine: bỏ qua {it['project']}: {e.message}", file=sys.stderr)
    events.emit_raw({"type": "routine_sync", "created": created, "skipped": skipped})
