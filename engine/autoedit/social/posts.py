"""Post helpers: normalising bundle.social posts, referenceKey, queue slots."""
from datetime import datetime, time, timedelta
from pathlib import Path

REF_PREFIX = "autoedit:"


def reference_key(project_dir: Path, run: int) -> str:
    return f"{REF_PREFIX}{Path(project_dir).name}:{int(run)}"


def parse_reference(key: str | None) -> tuple[str, int] | None:
    if not key or not key.startswith(REF_PREFIX):
        return None
    name, sep, run = key[len(REF_PREFIX):].rpartition(":")
    if not sep or not name or not run.isdigit():
        return None
    return name, int(run)


def _permalinks(raw: dict) -> dict:
    out = {}
    ext = raw.get("externalData")
    if isinstance(ext, dict):
        for typ, v in ext.items():
            link = v.get("permalink") if isinstance(v, dict) else None
            if isinstance(link, str) and link:
                out[typ] = link
    return out


def _error(raw: dict) -> str | None:
    errs = raw.get("errors")
    if isinstance(errs, dict):
        msgs = []
        for typ, v in errs.items():
            msg = v.get("errorMessage") or v.get("message") if isinstance(v, dict) else v
            if msg:
                msgs.append(f"{typ}: {msg}")
        return "; ".join(msgs) or None
    if isinstance(errs, str) and errs:
        return errs
    return None


def normalize(raw: dict) -> dict:
    types = raw.get("socialAccountTypes")
    if not isinstance(types, list):
        data = raw.get("data")
        types = list(data) if isinstance(data, dict) else []
    ref = parse_reference(raw.get("referenceKey"))
    return {"id": raw.get("id"), "title": raw.get("title") or "", "status": raw.get("status"),
            "postDate": raw.get("postDate"), "channels": types, "error": _error(raw),
            "project": ref[0] if ref else None, "run": ref[1] if ref else None,
            "permalinks": _permalinks(raw)}


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def near(a: datetime, b: datetime, minutes: int = 1) -> bool:
    if a.tzinfo is None:
        a = a.astimezone()
    if b.tzinfo is None:
        b = b.astimezone()
    return abs((a - b).total_seconds()) <= minutes * 60


def next_queue_slot(now: datetime, routines: list[dict], taken: list[str]) -> datetime:
    """Earliest routine slot (within 30 days) not within +-1 min of a taken post date; with no routine,
    19:30 tomorrow (first free day) in now's timezone."""
    from autoedit.social.routine import slots
    busy = []
    for t in taken:
        try:
            busy.append(parse_time(t))
        except ValueError:
            continue
    for dt, _ in slots(now, routines, days=30):
        if not any(near(dt, b) for b in busy):
            return dt
    day = now.date() + timedelta(days=1)
    while True:
        dt = datetime.combine(day, time(19, 30), tzinfo=now.tzinfo)
        if not any(near(dt, b) for b in busy):
            return dt
        day += timedelta(days=1)
