"""bundle.social REST client (stdlib urllib only). Only the endpoints listed in the M4 plan are wrapped."""
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from autoedit import __version__, secrets_env
from autoedit.errors import SocialAuth, SocialFailed, SocialLimit

DEFAULT_BASE = "https://api.bundle.social"
LARGE = 90 * 1024 * 1024       # above this: init -> PUT signed url -> finalize
TIMEOUT = 60
UPLOAD_TIMEOUT = 15 * 60
CHUNK = 1024 * 1024
MIME = "video/mp4"
# bundle.social (Cloudflare) answers 403 to the default "Python-urllib/x" agent
USER_AGENT = f"AutoEdit/{__version__}"


class _Body:
    """File-like request body: head + file + tail, streamed in chunks, reports progress."""

    def __init__(self, head: bytes, path: Path, tail: bytes, on_progress=None):
        self._head, self._tail, self._on = head, tail, on_progress
        self._f = open(path, "rb")
        self._size = path.stat().st_size
        self._sent = 0
        self._stage = 0
        self.length = len(head) + self._size + len(tail)

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.length
        if self._stage == 0:
            self._stage = 1
            return self._head
        if self._stage == 1:
            data = self._f.read(n)
            if data:
                self._sent += len(data)
                if self._on and self._size:
                    self._on(self._sent / self._size)
                return data
            self._stage = 2
        if self._stage == 2:
            self._stage = 3
            return self._tail
        return b""

    def close(self) -> None:
        self._f.close()


class _Raw:
    """Streams a file as the whole body (signed-url PUT)."""

    def __init__(self, path: Path, on_progress=None):
        self._f = open(path, "rb")
        self.length = path.stat().st_size
        self._sent, self._on = 0, on_progress

    def read(self, n: int = -1) -> bytes:
        data = self._f.read(n if n and n > 0 else CHUNK)
        self._sent += len(data)
        if data and self._on and self.length:
            self._on(self._sent / self.length)
        return data

    def close(self) -> None:
        self._f.close()


def _message(body: bytes) -> str | None:
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return None
    msg = data.get("message") if isinstance(data, dict) else None
    if isinstance(msg, list):
        msg = "; ".join(str(m) for m in msg)
    return str(msg) if msg else None


class Client:
    def __init__(self, key: str | None = None, base: str | None = None):
        self.key = key if key is not None else secrets_env.get("BUNDLE_SOCIAL_KEY")
        if not self.key:
            raise SocialAuth("Chưa nhập key bundle.social")
        self.base = (base or os.environ.get("BUNDLE_SOCIAL_BASE") or DEFAULT_BASE).rstrip("/")

    # -- transport ---------------------------------------------------------
    def _send(self, req: urllib.request.Request, timeout: int):
        req.add_header("User-Agent", USER_AGENT)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read() if e.fp else b""
            if e.code == 401:      # 403 is a plan/permission refusal, not a bad key: never make the app wipe the key
                raise SocialAuth("Key bundle.social không đúng hoặc đã bị thu hồi") from None
            if e.code == 403:
                raise SocialFailed(_message(body) or "bundle.social từ chối yêu cầu (gói hoặc quyền)") from None
            if e.code == 429:
                raise SocialLimit("bundle.social đang giới hạn, thử lại sau") from None
            raise SocialFailed(_message(body) or f"bundle.social trả lỗi {e.code}") from None
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise SocialFailed(f"Không kết nối được bundle.social: {getattr(e, 'reason', e)}") from None
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            raise SocialFailed("bundle.social trả dữ liệu không đọc được") from None

    def _request(self, method: str, path: str, *, query: dict | None = None, body: dict | None = None,
                 timeout: int = TIMEOUT):
        url = self.base + path
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        headers = {"x-api-key": self.key, "Accept": "application/json"}
        data = b"" if method == "POST" else None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        return self._send(urllib.request.Request(url, data=data, headers=headers, method=method), timeout)

    # -- organization ------------------------------------------------------
    def organization(self) -> dict:
        return self._request("GET", "/api/v1/organization/")

    def usage_posts(self) -> dict:
        return self._request("GET", "/api/v1/organization/usage/posts")

    def usage_uploads(self) -> dict:
        return self._request("GET", "/api/v1/organization/usage/uploads")

    def teams(self) -> list[dict]:
        out, offset, limit = [], 0, 50
        while True:
            page = self._request("GET", "/api/v1/team/", query={"offset": offset, "limit": limit})
            items = page.get("items") or []
            out += items
            offset += len(items)
            if not items or len(items) < limit or offset >= page.get("total", offset + 1):
                return out

    def team(self, id: str) -> dict:
        return self._request("GET", f"/api/v1/team/{urllib.parse.quote(id, safe='')}")

    def portal_link(self, team_id: str, types: list[str]) -> str:
        res = self._request("POST", "/api/v1/social-account/create-portal-link",
                            body={"teamId": team_id, "socialAccountTypes": types, "language": "en"})
        url = res.get("url")
        if not url:
            raise SocialFailed("bundle.social không trả đường dẫn kết nối")
        return url

    # -- uploads -----------------------------------------------------------
    def upload(self, team_id: str, path: Path, on_progress=None) -> str:
        path = Path(path)
        if path.stat().st_size > LARGE:
            return self._upload_large(team_id, path, on_progress)
        boundary = "autoedit" + secrets.token_hex(16)
        name = path.name.replace('"', "").replace("\r", "").replace("\n", "")
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"teamId\"\r\n\r\n{team_id}\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
                f"Content-Type: {MIME}\r\n\r\n").encode("utf-8")
        tail = f"\r\n--{boundary}--\r\n".encode()
        body = _Body(head, path, tail, on_progress)
        try:
            req = urllib.request.Request(
                self.base + "/api/v1/upload/", data=body, method="POST",
                headers={"x-api-key": self.key, "Accept": "application/json",
                         "Content-Type": f"multipart/form-data; boundary={boundary}",
                         "Content-Length": str(body.length)})
            res = self._send(req, UPLOAD_TIMEOUT)
        finally:
            body.close()
        return self._upload_id(res)

    def _upload_large(self, team_id: str, path: Path, on_progress) -> str:
        init = self._request("POST", "/api/v1/upload/init",
                             body={"teamId": team_id, "fileName": path.name, "mimeType": MIME,
                                   "fileSize": path.stat().st_size})
        url, remote = init.get("url"), init.get("path")
        if not url or not remote:
            raise SocialFailed("bundle.social không cấp được chỗ tải lên")
        body = _Raw(path, on_progress)
        try:
            # the signed url carries its own auth: never send our key there
            req = urllib.request.Request(url, data=body, method="PUT",
                                         headers={"Content-Type": MIME, "Content-Length": str(body.length),
                                                  "User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=UPLOAD_TIMEOUT):
                    pass
            except urllib.error.HTTPError as e:
                raise SocialFailed(f"Tải video lên lỗi ({e.code})") from None
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                raise SocialFailed(f"Tải video lên lỗi: {getattr(e, 'reason', e)}") from None
        finally:
            body.close()
        res = self._request("POST", "/api/v1/upload/finalize", body={"teamId": team_id, "path": remote})
        return self._upload_id(res)

    @staticmethod
    def _upload_id(res: dict) -> str:
        if not res.get("id"):
            raise SocialFailed("bundle.social không trả id video đã tải")
        return res["id"]

    def tiktok_post_settings(self, team_id: str) -> dict:
        return self._request("GET", "/api/v1/misc/tiktok/post-settings", query={"teamId": team_id})

    # -- posts -------------------------------------------------------------
    def create_post(self, body: dict) -> dict:
        return self._request("POST", "/api/v1/post/", body=body)

    def list_posts(self, team_id: str, start: str, end: str) -> list[dict]:
        out, offset, limit = [], 0, 100
        while True:
            page = self._request("GET", "/api/v1/post/", query={
                "teamId": team_id, "postDateFrom": start, "postDateTo": end,
                "orderBy": "postDate", "order": "ASC", "offset": offset, "limit": limit})
            items = page.get("items") or []
            out += items
            offset += len(items)
            if not items or len(items) < limit or offset >= page.get("total", offset + 1):
                return out

    def get_post(self, id: str) -> dict:
        return self._request("GET", f"/api/v1/post/{urllib.parse.quote(id, safe='')}")

    def retry_post(self, id: str) -> dict:
        return self._request("POST", f"/api/v1/post/{urllib.parse.quote(id, safe='')}/retry")
