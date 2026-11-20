"""Daily routines: pure planning of which unposted video goes to which slot."""
from datetime import datetime, time, timedelta

from autoedit.social.posts import near, parse_reference, parse_time


def _hhmm(value: str) -> time | None:
    try:
        h, m = value.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def slots(now: datetime, routines: list[dict], days: int = 7) -> list[tuple[datetime, dict]]:
    """Every slot of an enabled routine in [now, now+days), by time. Each slot is local wall-clock time on its
    own date (`.astimezone()` picks that date's UTC offset), so a DST change inside the window keeps 19:30 at 19:30."""
    end = now + timedelta(days=days)
    today = now.astimezone().date()
    out = []
    for r in routines:
        t = _hhmm(r.get("time")) if r.get("enabled") else None
        if t is None:
            continue
        for d in range(days + 1):
            dt = datetime.combine(today + timedelta(days=d), t).astimezone()
            if now <= dt < end:
                out.append((dt, r))
    out.sort(key=lambda s: s[0])
    return out


def _ref_project(post: dict) -> str | None:
    ref = parse_reference(post.get("referenceKey"))
    return ref[0] if ref else post.get("project")


def plan(now: datetime, routines: list[dict], videos: list[dict], existing: list[dict]) -> list[dict]:
    """videos: [{"project", "run", "created", "posted"?}] (any number of runs per project).
    existing: posts already on bundle.social (raw or normalized). Newest unposted project goes to the earliest free slot."""
    already = {p for p in map(_ref_project, existing) if p}
    latest: dict[str, dict] = {}
    for v in videos:
        if v.get("posted") or v["project"] in already:
            continue
        cur = latest.get(v["project"])
        if cur is None or v["run"] > cur["run"]:
            latest[v["project"]] = v
    queue = sorted(latest.values(), key=lambda v: v["created"], reverse=True)
    mine = []
    for p in existing:
        if (p.get("referenceKey") or "").startswith("autoedit:") or p.get("project"):
            try:
                mine.append(parse_time(p["postDate"]))
            except (KeyError, ValueError, TypeError):
                pass
    out = []
    for dt, r in slots(now, routines):
        if not queue:
            break
        if any(near(dt, m) for m in mine):
            continue
        v = queue.pop(0)
        out.append({"slot": dt.isoformat(timespec="seconds"), "channels": list(r.get("channels") or []),
                    "project": v["project"], "run": v["run"]})
    return out
