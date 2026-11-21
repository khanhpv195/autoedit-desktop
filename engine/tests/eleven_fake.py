"""Local fake ElevenLabs server for tests (never the real API). Same shape as social_fake.FakeBundle."""
import base64

from social_fake import FakeBundle

FAKE_MP3 = b"ID3fake-mp3-bytes"


def alignment_for(text: str, step: float = 0.1) -> dict:
    chars = list(text)
    return {"characters": chars,
            "character_start_times_seconds": [round(i * step, 3) for i in range(len(chars))],
            "character_end_times_seconds": [round((i + 1) * step, 3) for i in range(len(chars))]}


def tts_ok(req):
    body = req.json()
    return 200, {"audio_base64": base64.b64encode(FAKE_MP3).decode(), "alignment": alignment_for(body["text"]),
                 "normalized_alignment": alignment_for(body["text"])}


class FakeEleven(FakeBundle):
    """`routes` as in FakeBundle; defaults: subscription 10000/2500 and a working TTS for voice v1."""

    def __init__(self, routes: dict | None = None):
        base = {("GET", "/v1/user/subscription"): (200, {"character_limit": 10000, "character_count": 2500}),
                ("POST", "/v1/text-to-speech/v1/with-timestamps"): tts_ok}
        super().__init__(base | dict(routes or {}))
