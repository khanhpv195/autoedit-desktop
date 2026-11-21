"""ElevenLabs text-to-speech client (stdlib urllib only). Never logs or echoes the key."""
import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from autoedit import __version__, secrets_env
from autoedit.errors import VoiceAuth, VoiceFailed, VoiceLimit, VoiceMissing, VoiceQuota
from autoedit.fsutil import atomic_write_text

DEFAULT_BASE = "https://api.elevenlabs.io"
MODEL_ID = "eleven_v4"
LANGUAGE = "vi"
OUTPUT_FORMAT = "mp3_44100_128"
TIMEOUT = 60
USER_AGENT = f"AutoEdit/{__version__}"

MSG_AUTH = "Key ElevenLabs không đúng"
MSG_QUOTA = "Tài khoản ElevenLabs hết ký tự"
MSG_MISSING = "Giọng đọc không còn trong tài khoản ElevenLabs, chọn giọng khác trong Cài đặt"
MSG_LIMIT = "ElevenLabs đang bận, thử lại sau"
MSG_FAILED = "Lồng tiếng ElevenLabs bị lỗi"
MSG_OFFLINE = "Không kết nối được ElevenLabs, kiểm tra mạng rồi thử lại"

Word = tuple[str, float, float]


def _base() -> str:
    return os.environ.get("ELEVENLABS_BASE", DEFAULT_BASE).rstrip("/")


def _key() -> str:
    key = secrets_env.get("ELEVENLABS_API_KEY")
    if not key:
        raise VoiceAuth(MSG_AUTH)
    return key


def _error(status: int, body: bytes) -> Exception:
    try:
        data = json.loads(body.decode("utf-8", "replace") or "{}")
    except ValueError:
        data = {}
    detail = data.get("detail") if isinstance(data, dict) else None
    status_field = detail.get("status") if isinstance(detail, dict) else None
    text = json.dumps(detail, ensure_ascii=False).lower() if detail is not None else ""
    if status == 401 and status_field == "quota_exceeded" or status == 402:
        return VoiceQuota(MSG_QUOTA)
    if status == 401:
        return VoiceAuth(MSG_AUTH)
    if status == 404 or (status == 422 and "voice" in text):
        return VoiceMissing(MSG_MISSING)
    if status == 429:
        return VoiceLimit(MSG_LIMIT)
    return VoiceFailed(f"{MSG_FAILED} (HTTP {status})")


def _request(method: str, path: str, body: dict | None = None) -> dict:
    headers = {"xi-api-key": _key(), "User-Agent": USER_AGENT, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(_base() + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise _error(e.code, e.read() or b"") from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise VoiceFailed(MSG_OFFLINE) from None
    try:
        out = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise VoiceFailed(f"{MSG_FAILED} (trả lời không hợp lệ)") from None
    if not isinstance(out, dict):
        raise VoiceFailed(f"{MSG_FAILED} (trả lời không hợp lệ)")
    return out


def quota() -> int:
    """Characters left this billing period."""
    d = _request("GET", "/v1/user/subscription")
    try:
        return int(d["character_limit"]) - int(d["character_count"])
    except (KeyError, TypeError, ValueError):
        raise VoiceFailed(f"{MSG_FAILED} (không đọc được số ký tự)") from None


def alignment_to_words(alignment: dict) -> list[Word]:
    """Character timings -> words (split on whitespace), each (text, start, end) in seconds."""
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    words: list[Word] = []
    cur, a, b = "", 0.0, 0.0
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append((cur, a, b))
            cur = ""
            continue
        if not cur:
            a = float(s)
        cur += ch
        b = float(e)
    if cur:
        words.append((cur, a, b))
    return words


def cache_key(voice_id: str, text: str) -> str:
    return hashlib.sha1(f"{voice_id}|{MODEL_ID}|{text}".encode("utf-8")).hexdigest()


def _paths(voice_id: str, text: str, cache_dir: Path) -> tuple[Path, Path]:
    h = cache_key(voice_id, text)
    return Path(cache_dir) / f"{h}.mp3", Path(cache_dir) / f"{h}.json"


def cached(text: str, voice_id: str, cache_dir: Path) -> tuple[Path, list[Word]] | None:
    """Cache-only lookup (never HTTP): (mp3, words) if the line is fully cached, else None."""
    mp3, js = _paths(voice_id, text, cache_dir)
    if not (mp3.is_file() and js.is_file()):
        return None
    try:
        return mp3, [(str(w), float(a), float(b)) for w, a, b in json.loads(js.read_text(encoding="utf-8"))]
    except (OSError, ValueError, TypeError):
        return None     # a damaged entry is a miss: tts() re-synthesizes it


def tts(text: str, voice_id: str, cache_dir: Path) -> tuple[Path, list[Word]]:
    """Synthesize `text` (Vietnamese) with timestamps. Cached by (voice, model, text): a hit makes no HTTP call."""
    hit = cached(text, voice_id, cache_dir)
    if hit is not None:
        return hit
    mp3, js = _paths(voice_id, text, cache_dir)
    d = _request("POST", f"/v1/text-to-speech/{voice_id}/with-timestamps",
                 {"text": text, "model_id": MODEL_ID, "language_code": LANGUAGE, "output_format": OUTPUT_FORMAT})
    try:
        audio = base64.b64decode(d["audio_base64"], validate=True)
    except (KeyError, TypeError, ValueError):
        raise VoiceFailed(f"{MSG_FAILED} (không có âm thanh)") from None
    if not audio:
        raise VoiceFailed(f"{MSG_FAILED} (không có âm thanh)")
    words = alignment_to_words(d.get("alignment") or d.get("normalized_alignment") or {})
    mp3.parent.mkdir(parents=True, exist_ok=True)
    tmp = mp3.with_suffix(".mp3.part")
    tmp.write_bytes(audio)
    os.replace(tmp, mp3)
    atomic_write_text(js, json.dumps(words, ensure_ascii=False))     # json last: it marks the entry complete
    return mp3, words
