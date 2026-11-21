import base64
import hashlib
import json
import socket

import pytest

from autoedit import secrets_env
from autoedit.errors import VoiceAuth, VoiceFailed, VoiceLimit, VoiceMissing, VoiceQuota
from autoedit.voice import eleven
from eleven_fake import FAKE_MP3, FakeEleven

TTS = ("POST", "/v1/text-to-speech/v1/with-timestamps")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    def use(fake):
        monkeypatch.setenv("ELEVENLABS_BASE", fake.url)
    return use


def test_alignment_to_words_groups_on_whitespace():
    chars = list("Áo  len\ncổ lọ ")
    al = {"characters": chars, "character_start_times_seconds": [i * 0.1 for i in range(len(chars))],
          "character_end_times_seconds": [i * 0.1 + 0.1 for i in range(len(chars))]}
    words = eleven.alignment_to_words(al)
    assert [w[0] for w in words] == ["Áo", "len", "cổ", "lọ"]
    assert words[0][1] == pytest.approx(0.0) and words[0][2] == pytest.approx(0.2)
    assert words[1][1] == pytest.approx(0.4) and words[1][2] == pytest.approx(0.7)
    assert eleven.alignment_to_words({}) == []


def test_tts_roundtrip_and_cache(env, tmp_path):
    with FakeEleven() as fake:
        env(fake)
        path, words = eleven.tts("Áo len đẹp", "v1", tmp_path / "vo")
        assert path.read_bytes() == FAKE_MP3 and [w[0] for w in words] == ["Áo", "len", "đẹp"]
        h = hashlib.sha1(f"v1|{eleven.MODEL_ID}|Áo len đẹp".encode()).hexdigest()
        assert path == tmp_path / "vo" / f"{h}.mp3"
        assert json.loads((tmp_path / "vo" / f"{h}.json").read_text(encoding="utf-8"))[0][0] == "Áo"
        req = fake.calls(*TTS)[0]
        assert req.headers["xi-api-key"] == "test-key" and req.headers["user-agent"].startswith("AutoEdit/")
        assert req.json() == {"text": "Áo len đẹp", "model_id": "eleven_v4", "language_code": "vi",
                              "output_format": "mp3_44100_128"}
        again = eleven.tts("Áo len đẹp", "v1", tmp_path / "vo")
        assert again == (path, words) and len(fake.calls(*TTS)) == 1     # cache hit: no HTTP


def test_cache_hit_needs_no_key(tmp_path, monkeypatch):
    d = tmp_path / "vo"; d.mkdir()
    h = eleven.cache_key("v1", "xin chào")
    (d / f"{h}.mp3").write_bytes(FAKE_MP3)
    (d / f"{h}.json").write_text(json.dumps([["xin", 0, 0.2], ["chào", 0.3, 0.5]]))
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    path, words = eleven.tts("xin chào", "v1", d)
    assert words == [("xin", 0, 0.2), ("chào", 0.3, 0.5)]
    assert eleven.cached("xin chào", "v1", d) == (path, words)


def test_cached_lookup_makes_no_http(tmp_path, monkeypatch):
    monkeypatch.setattr(eleven, "_request", lambda *a, **k: pytest.fail("no HTTP on a cache lookup"))
    assert eleven.cached("chưa có", "v1", tmp_path / "vo") is None
    d = tmp_path / "vo"; d.mkdir()
    h = eleven.cache_key("v1", "chỉ mp3")
    (d / f"{h}.mp3").write_bytes(FAKE_MP3)     # no json: the entry is incomplete
    assert eleven.cached("chỉ mp3", "v1", d) is None


@pytest.mark.parametrize("status,body,cls", [
    (401, {"detail": {"status": "invalid_api_key", "message": "bad"}}, VoiceAuth),
    (401, {"detail": {"status": "quota_exceeded", "message": "no chars"}}, VoiceQuota),
    (402, {"detail": {"status": "payment_required"}}, VoiceQuota),
    (404, {"detail": {"status": "voice_not_found", "message": "voice not found"}}, VoiceMissing),
    (422, {"detail": {"status": "invalid_voice", "message": "voice_id is invalid"}}, VoiceMissing),
    (422, {"detail": [{"msg": "text too long"}]}, VoiceFailed),
    (429, {"detail": {"status": "too_many_concurrent_requests"}}, VoiceLimit),
    (500, {"detail": "oops"}, VoiceFailed),
])
def test_error_mapping(env, tmp_path, status, body, cls):
    with FakeEleven({TTS: (status, body)}) as fake:
        env(fake)
        with pytest.raises(cls) as e:
            eleven.tts("chào", "v1", tmp_path)
        assert "test-key" not in e.value.message
    assert not list(tmp_path.glob("*.mp3"))


def test_messages_are_vietnamese():
    assert eleven.MSG_AUTH == "Key ElevenLabs không đúng"
    assert eleven.MSG_QUOTA == "Tài khoản ElevenLabs hết ký tự"
    assert eleven.MSG_MISSING == "Giọng đọc không còn trong tài khoản ElevenLabs, chọn giọng khác trong Cài đặt"
    assert eleven.MSG_LIMIT == "ElevenLabs đang bận, thử lại sau"
    assert VoiceAuth.code == "VOICE_AUTH" and VoiceQuota.code == "VOICE_QUOTA" and VoiceMissing.code == "VOICE_MISSING"
    assert VoiceLimit.code == "VOICE_LIMIT" and VoiceFailed.code == "VOICE_FAILED"


def test_connection_refused_is_voice_failed(monkeypatch, tmp_path):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_BASE", f"http://127.0.0.1:{port}")
    with pytest.raises(VoiceFailed):
        eleven.tts("chào", "v1", tmp_path)
    with pytest.raises(VoiceFailed):
        eleven.quota()


def test_missing_key_is_voice_auth(monkeypatch, tmp_path):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(VoiceAuth):
        eleven.tts("chào", "v1", tmp_path)
    with pytest.raises(VoiceAuth):
        eleven.quota()


def test_quota(env):
    with FakeEleven() as fake:
        env(fake)
        assert eleven.quota() == 7500
        assert fake.calls("GET", "/v1/user/subscription")[0].headers["xi-api-key"] == "test-key"


def test_key_comes_from_scrubbed_secrets(monkeypatch):
    assert "ELEVENLABS_API_KEY" in secrets_env.SECRET_NAMES
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    secrets_env.scrub()
    import os
    assert "ELEVENLABS_API_KEY" not in os.environ and secrets_env.get("ELEVENLABS_API_KEY") == "test-key"


def test_bad_audio_payload_is_voice_failed(env, tmp_path):
    with FakeEleven({TTS: (200, {"alignment": {}})}) as fake:
        env(fake)
        with pytest.raises(VoiceFailed):
            eleven.tts("chào", "v1", tmp_path)
