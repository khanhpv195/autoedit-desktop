import hashlib
import json
import re
import tempfile
from pathlib import Path

from autoedit import bins
from autoedit.errors import RenderFailed
from autoedit.fsutil import atomic_write_text
from autoedit.transcript import Word, pack_phrases, words_from_json, words_to_json

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


CLOSING = re.compile(
    r"cảm ơn (?:các )?(?:bạn|anh chị em|mọi người|quý vị)(?: rất nhiều)?(?: đã)? (?:xem|theo dõi|lắng nghe)"
    r"|(?:(?:hãy|nhớ|các bạn hãy) )?(?:đăng ký|subscribe|theo dõi)(?: cho)? (?:kênh|channel)"
    r"|(?:(?:hãy|nhớ) )?\bsubscribe\b|ghiền mì gõ|để không bỏ lỡ(?: những video(?: hấp dẫn)?)?|hẹn gặp lại(?: các bạn)? trong"
    r"|like (?:và|&) (?:share|subscribe)|đừng quên (?:like|đăng ký)")
SALES = re.compile(
    r"(?<!\w)(?:giỏ hàng|bấm|mua|đặt|inbox|link|mã giảm giá|shop|like|share|giá|freeship)(?!\w)")
WHOLE_PHRASE = 0.5     # a closing pattern must cover at least this share of the phrase's characters
ISOLATION = 2.0


def _norm(text: str) -> str:
    return re.sub(r"[^\w&]+", " ", text.casefold()).strip()


def _is_closing(phrase_text: str) -> bool:
    """The whole phrase is a closing line: a pattern covers most of it and nothing in it sells."""
    t = _norm(phrase_text)
    if not t or SALES.search(t):
        return False
    covered = sum(m.end() - m.start() for m in CLOSING.finditer(t))
    return covered >= WHOLE_PHRASE * len(t)


STRETCHED = 0.6       # mean seconds per word; real Vietnamese speech is ~0.2-0.35


def _drop_stretched_tail(words: list[Word]) -> list[Word]:
    """Whisper over a trailing silent or music-only clip invents outros glued to the last real words (no gap, so
    they share a phrase). Drop the shortest-start tail that begins with a closing line, is mostly closing text,
    has no sales term, and is either stretched (>= STRETCHED s per word) or repeats a closing line."""
    best = None
    for k in range(len(words) - 1, max(-1, len(words) - 120), -1):
        tail = words[k:]
        t = _norm(" ".join(w.text for w in tail))
        if SALES.search(t):
            break
        m = list(CLOSING.finditer(t))
        if not m or m[0].start() != 0 or not _is_closing(" ".join(w.text for w in tail)):
            continue
        per_word = sum(w.end - w.start for w in tail) / len(tail)    # spoken length, gaps excluded
        texts = [x.group(0) for x in m]
        if per_word >= STRETCHED or len(texts) != len(set(texts)):
            best = k
    return words[:best] if best is not None else words


def drop_closing_lines(words: list[Word]) -> list[Word]:
    """Whisper invents YouTube-style outros ("cảm ơn các bạn đã theo dõi", "hãy đăng ký kênh") over silence or
    music, with real durations. Drop (1) trailing whole phrases at the very end of the transcript that are closing
    lines without any sales term, and (2) such a phrase alone in a silent region (>=2 s of silence on both sides).
    Words after a non-matching phrase are never deleted."""
    if not words:
        return words
    words = _drop_stretched_tail(words)
    if not words:
        return words
    phrases = pack_phrases(words)
    keep = len(phrases)
    while keep and _is_closing(phrases[keep - 1].text):
        keep -= 1
    drop: set[int] = set()
    pos = 0
    spans = []
    for p in phrases:
        n = len(p.text.split())
        spans.append((pos, pos + n))
        pos += n
    for k in range(keep, len(phrases)):
        drop.update(range(*spans[k]))
    # 2) isolated outro phrases
    for k, p in enumerate(phrases[:keep]):
        before = p.start - phrases[k - 1].end if k else ISOLATION
        after = phrases[k + 1].start - p.end if k + 1 < len(phrases) else ISOLATION
        if before >= ISOLATION and after >= ISOLATION and _is_closing(p.text):
            drop.update(range(*spans[k]))
    return [w for i, w in enumerate(words) if i not in drop]


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
    return drop_closing_lines(drop_hallucinations(parse_whisper_json(data)))


def transcribe(video: Path, work_dir: Path, language: str = "vi") -> list[Word]:
    cache = work_dir / "transcript.json"
    digest = _sha256(video)
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("sha256") == digest:
                return drop_closing_lines(words_from_json(data["words"]))    # filters improve; caches stay
        except (ValueError, KeyError, TypeError):
            pass    # corrupt or half-written cache: transcribe again
    words = _run_whisper(video, work_dir, language)
    work_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(cache, json.dumps({"sha256": digest, "words": words_to_json(words)}, ensure_ascii=False))
    return words
