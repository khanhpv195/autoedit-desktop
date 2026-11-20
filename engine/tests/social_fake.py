"""Local fake bundle.social server for tests (never the real API)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class Req:
    def __init__(self, method, path, query, headers, body):
        self.method, self.path, self.query, self.headers, self.body = method, path, query, headers, body

    def json(self):
        return json.loads(self.body or b"{}")


class FakeBundle:
    """Context manager. `routes[(METHOD, path)]` = (status, obj) or callable(Req) -> (status, obj).
    Unknown routes answer 404 {"message": "no route"}. Received requests land in `requests`."""

    def __init__(self, routes: dict | None = None):
        self.routes = dict(routes or {})
        self.requests: list[Req] = []
        self.url = ""
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _handle(self):
                parts = urlsplit(self.path)
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                req = Req(self.command, parts.path, {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parts.query).items()},
                          {k.lower(): v for k, v in self.headers.items()}, body)
                fake.requests.append(req)
                route = fake.routes.get((self.command, parts.path))
                if route is None:
                    status, obj = 404, {"message": "no route"}
                else:
                    status, obj = route(req) if callable(route) else route
                data = b"" if obj is None else json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = _handle

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self._srv.daemon_threads = True

    def __enter__(self):
        self.url = f"http://127.0.0.1:{self._srv.server_address[1]}"
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self._srv.shutdown()
        self._srv.server_close()

    def calls(self, method: str, path: str) -> list[Req]:
        return [r for r in self.requests if r.method == method and r.path == path]
