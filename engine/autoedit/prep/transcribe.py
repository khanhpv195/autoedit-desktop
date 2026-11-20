import hashlib
import json
import tempfile
from pathlib import Path

from autoedit import bins
from autoedit.errors import RenderFailed
from autoedit.transcript import Word, words_from_json, words_to_json

WHISPER_LAG = 0.10


def parse_whisper_json(data: dict, lag: float = WHISPER_LAG) -> list[Word]:
    words = []
    for seg in data.get("transcription", []):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        off = seg["offsets"]
        start, end = off["from"] / 1000 + lag, off["to"] / 1000 + lag
        words.append(Word(text, round(start, 3), round(max(end, start), 3)))
    return words


def drop_hallucinations(words: list[Word]) -> list[Word]:
    """Whisper's invented lines get no acoustic alignment: runs of >=3 near-zero-length words."""
    out: list[Word] = []
    i = 0
    while i < len(words):
        j = i
        while (j < len(words) and words[j].end - words[j].start < 0.05
               and (j == i or words[j].start - words[j - 1].end < 0.5)):
            j += 1
        if j - i >= 3:
            i = j
            continue
        out.extend(words[i:max(j, i + 1)])
        i = max(j, i + 1)
    return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_whisper(video: Path, work_dir: Path, language: str) -> list[Word]:
    model = bins.model_path()
    if not model.exists():
        raise RenderFailed("Chưa tải model nhận giọng nói")
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        bins.run([bins.tool_path("ffmpeg"), "-y", "-v", "error", "-i", str(video),
                  "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)])
        base = Path(tmp) / "out"
        bins.run([bins.tool_path("whisper-cli"), "-m", str(model), "-f", str(wav), "-l", language,
                  "-ml", "1", "-sow", "-oj", "-of", str(base)])
        data = json.loads((base.with_suffix(".json")).read_text(encoding="utf-8"))
    return drop_hallucinations(parse_whisper_json(data))


def transcribe(video: Path, work_dir: Path, language: str = "vi") -> list[Word]:
    cache = work_dir / "transcript.json"
    digest = _sha256(video)
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        if data.get("sha256") == digest:
            return words_from_json(data["words"])
    words = _run_whisper(video, work_dir, language)
    work_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"sha256": digest, "words": words_to_json(words)}, ensure_ascii=False),
                     encoding="utf-8")
    return words
