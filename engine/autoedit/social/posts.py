"""Post helpers: normalising bundle.social posts, referenceKey, queue slots."""
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


def next_queue_slot(now, routines, taken):   # replaced in the routine task
    raise NotImplementedError
