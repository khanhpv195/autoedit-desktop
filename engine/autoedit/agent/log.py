"""JSON-lines record of every SDK message for runs/N/agent.jsonl. Image bytes and secrets never reach the log."""
import dataclasses
import re

SECRET_KEY = re.compile(r"(?i)(^|_)(api_?key|secret|password|authorization|oauth_?token|auth_?token|token)$|^env$")


def _clean(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        obj = {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        if obj.get("type") == "image":
            raw = obj.get("data") or (obj.get("source") or {}).get("data") or ""
            return {"type": "image", "note": f"image omitted ({len(raw)} base64 chars)"}
        return {k: ("<redacted>" if isinstance(k, str) and SECRET_KEY.search(k) else _clean(v))
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(x) for x in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def serialize_message(msg) -> dict:
    rec = _clean(msg)
    rec = rec if isinstance(rec, dict) else {"value": rec}
    return {"type": "sdk", "kind": type(msg).__name__, **{k: v for k, v in rec.items() if k != "type"}}
