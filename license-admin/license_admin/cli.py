import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "AutoEdit-License-Admin/1"


def config_path() -> Path:
    return Path(os.environ.get("AUTOEDIT_LICENSE_CONFIG") or Path.home() / ".autoedit-license" / "config.json")


def load_config() -> dict:
    p = config_path()
    if not p.exists():
        raise SystemExit("Chưa cấu hình. Chạy: license-admin setup")
    return json.loads(p.read_text(encoding="utf-8"))


class ApiError(Exception):
    pass


def call(cfg: dict, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(cfg["url"] + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {cfg['admin_token']}")
    req.add_header("User-Agent", USER_AGENT)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ApiError("Admin token sai. Chạy lại: license-admin setup") from None
        if e.code == 404:
            raise ApiError("Không có key này") from None
        raise ApiError(f"Máy chủ trả lỗi {e.code}") from None
    except urllib.error.URLError as e:
        raise ApiError(f"Không kết nối được máy chủ: {e.reason}") from None


def norm(key: str) -> str:
    return key.strip().upper()


def cmd_setup(_a) -> int:
    url = input("URL của Worker (https://...workers.dev): ").strip().rstrip("/")
    token = getpass.getpass("Admin token: ").strip()
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"url": url, "admin_token": token}, f)
    os.chmod(p, 0o600)
    print(f"Đã lưu cấu hình vào {p}")
    return 0


def cmd_create(a) -> int:
    r = call(load_config(), "POST", "/v1/admin/keys", {"name": a.name, "note": a.note or ""})
    print(r["key"])
    return 0


def cmd_list(_a) -> int:
    keys = call(load_config(), "GET", "/v1/admin/keys")["keys"]
    rows = [("KEY", "KHÁCH", "TRẠNG THÁI", "MÁY", "KÍCH HOẠT", "LẦN CUỐI")]
    for k in keys:
        rows.append((k["key"], k["name"], k["status"], (k.get("machine") or "-")[:8],
                     (k.get("activated_at") or "-")[:10], (k.get("last_seen_at") or "-")[:16].replace("T", " ")))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))
    return 0


def cmd_action(a) -> int:
    call(load_config(), "POST", f"/v1/admin/keys/{urllib.parse.quote(norm(a.key))}/{a.cmd}", {})
    print("Đã thu hồi" if a.cmd == "revoke" else "Đã reset: key kích hoạt lại được trên một máy mới")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="license-admin")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup").set_defaults(fn=cmd_setup)
    c = sub.add_parser("create")
    c.add_argument("name")
    c.add_argument("--note")
    c.set_defaults(fn=cmd_create)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    for name in ("revoke", "reset"):
        x = sub.add_parser(name)
        x.add_argument("key")
        x.set_defaults(fn=cmd_action)
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except ApiError as e:
        print(str(e), file=sys.stderr)
        return 1
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
