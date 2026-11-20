"""Download the Whisper model once, resumably, sha256-checked."""
import hashlib
import os
import urllib.request
from pathlib import Path

from autoedit.bins import model_path
from autoedit.errors import SetupRequired
from autoedit.events import Emitter

MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"
MODEL_SIZE = 1624555275
MODEL_SHA256 = "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69"
CHUNK = 1 << 20


def install_model(events: Emitter, *, opener=urllib.request.urlopen, target: Path | None = None) -> Path:
    target = Path(target or model_path())
    if target.exists() and target.stat().st_size == MODEL_SIZE:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(MODEL_URL, headers={"Range": f"bytes={have}-"} if have else {})
    try:
        with opener(req) as resp:
            if have and getattr(resp, "status", 200) != 206:
                have = 0
            mode = "ab" if have else "wb"
            done, last = have, -1
            with open(part, mode) as f:
                while chunk := resp.read(CHUNK):
                    f.write(chunk)
                    done += len(chunk)
                    pct = done * 100 // MODEL_SIZE
                    if pct != last:
                        last = pct
                        events.step(f"Đang tải model giọng nói… {min(pct, 100)}%", min(done / MODEL_SIZE, 1.0))
    except OSError as e:
        raise SetupRequired(f"Không tải được model: {e}") from e
    digest = hashlib.sha256()
    with open(part, "rb") as f:
        while chunk := f.read(CHUNK):
            digest.update(chunk)
    if digest.hexdigest() != MODEL_SHA256:
        part.unlink(missing_ok=True)
        raise SetupRequired("Model tải về bị lỗi, thử lại")
    os.replace(part, target)
    events.step("Đã tải model giọng nói", 1.0)
    return target
