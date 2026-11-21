import json
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from license_admin import cli


class Fake:
    def __init__(self):
        self.requests = []
        self.keys = [{"key": "AE-AAAA-BBBB-CCCC-DDDD", "name": "Shop A", "note": "", "status": "active",
                      "machine": "0123456789abcdef0123456789abcdef", "activated_at": "2026-11-21T10:00:00Z",
                      "last_seen_at": "2026-11-21T11:00:00Z", "created_at": "2026-11-21T09:00:00Z"}]

    def __enter__(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _handle(self, method):
                n = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(n) if n else b""
                fake.requests.append({"method": method, "path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()},
                                      "body": json.loads(raw) if raw else None})
                if self.headers.get("authorization") != "Bearer tok":
                    return self._reply(401, {"error": "unauthorized"})
                if method == "GET" and self.path == "/v1/admin/keys":
                    return self._reply(200, {"keys": fake.keys})
                if method == "POST" and self.path == "/v1/admin/keys":
                    return self._reply(200, {"key": "AE-NEW0-0000-0000-0001"})
                if method == "POST" and self.path.endswith(("/revoke", "/reset")):
                    if "AE-AAAA-BBBB-CCCC-DDDD" in self.path:
                        return self._reply(200, {"ok": True})
                    return self._reply(404, {"error": "invalid"})
                return self._reply(404, {"error": "not_found"})

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    p = tmp_path / "cfg" / "config.json"
    monkeypatch.setenv("AUTOEDIT_LICENSE_CONFIG", str(p))
    return p


def write_cfg(p, url, token="tok"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"url": url, "admin_token": token}))


def test_setup_writes_private_config(cfg, monkeypatch):
    answers = iter(["https://lic.example.workers.dev/"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: "tok")
    assert cli.main(["setup"]) == 0
    data = json.loads(cfg.read_text())
    assert data == {"url": "https://lic.example.workers.dev", "admin_token": "tok"}
    if os.name == "posix":
        assert stat.S_IMODE(cfg.stat().st_mode) == 0o600


def test_create_prints_key_and_sends_auth_and_user_agent(cfg, capsys):
    with Fake() as f:
        write_cfg(cfg, f.url)
        assert cli.main(["create", "Shop B", "--note", "zalo 09"]) == 0
        r = f.requests[0]
        assert r["body"] == {"name": "Shop B", "note": "zalo 09"}
        assert r["headers"]["user-agent"].startswith("AutoEdit-License-Admin/")
    assert "AE-NEW0-0000-0000-0001" in capsys.readouterr().out


def test_list_shows_table(cfg, capsys):
    with Fake() as f:
        write_cfg(cfg, f.url)
        assert cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "AE-AAAA-BBBB-CCCC-DDDD" in out and "Shop A" in out and "active" in out and "01234567" in out


def test_revoke_and_reset(cfg, capsys):
    with Fake() as f:
        write_cfg(cfg, f.url)
        assert cli.main(["revoke", "ae-aaaa-bbbb-cccc-dddd"]) == 0
        assert cli.main(["reset", "AE-AAAA-BBBB-CCCC-DDDD"]) == 0
        assert [r["path"] for r in f.requests] == ["/v1/admin/keys/AE-AAAA-BBBB-CCCC-DDDD/revoke",
                                                   "/v1/admin/keys/AE-AAAA-BBBB-CCCC-DDDD/reset"]


def test_unknown_key_and_bad_token_exit_nonzero(cfg, capsys):
    with Fake() as f:
        write_cfg(cfg, f.url)
        assert cli.main(["revoke", "AE-ZZZZ-ZZZZ-ZZZZ-ZZZZ"]) == 1
        assert "Không có key" in capsys.readouterr().err
        write_cfg(cfg, f.url, token="wrong")
        assert cli.main(["list"]) == 1
        assert "Admin token sai" in capsys.readouterr().err


def test_missing_config(cfg, capsys):
    assert cli.main(["list"]) == 1
    assert "license-admin setup" in capsys.readouterr().err


def test_norm_matches_shared_vectors():
    import json
    from pathlib import Path
    from license_admin.cli import norm
    vectors = json.loads((Path(__file__).parents[2] / "license-server" / "test" / "key-vectors.json").read_text(encoding="utf-8"))
    assert len(vectors) >= 8
    for raw, want in vectors:
        assert norm(raw) == want, raw
