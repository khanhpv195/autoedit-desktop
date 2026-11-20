import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Phrase:
    start: float
    end: float
    text: str


def pack_phrases(words: list[Word], gap: float = 0.5) -> list[Phrase]:
    phrases: list[Phrase] = []
    cur: list[Word] = []
    for w in words:
        if cur and w.start - cur[-1].end >= gap:
            phrases.append(Phrase(cur[0].start, cur[-1].end, " ".join(x.text for x in cur)))
            cur = []
        cur.append(w)
    if cur:
        phrases.append(Phrase(cur[0].start, cur[-1].end, " ".join(x.text for x in cur)))
    return phrases


def format_phrases(phrases: list[Phrase]) -> str:
    return "\n".join(f"[{p.start:.2f}-{p.end:.2f}] {p.text}" for p in phrases)


def format_words(words: list[Word]) -> str:
    """Compact word list with source start times: `[12.34] giá [12.60] 189K`."""
    return " ".join(f"[{w.start:.2f}] {w.text}" for w in words)


def speech_duration(words: list[Word]) -> float:
    return sum(p.end - p.start for p in pack_phrases(words))


def words_to_json(words: list[Word]) -> list[dict]:
    return [{"text": w.text, "start": w.start, "end": w.end} for w in words]


def words_from_json(data: list[dict]) -> list[Word]:
    return [Word(d["text"], float(d["start"]), float(d["end"])) for d in data]


MATCH_WINDOW = 1.0
_PUNCT = ".,?!;:\"'()…"


def norm_token(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold().strip(_PUNCT)


def find_match(words: list[Word], target: str, at: float, window: float = MATCH_WINDOW) -> int | None:
    """Index of the first word of the sequence `target` (normalized text) nearest to time `at`.
    Only candidates within +-window s of `at` count; failing that, a text that occurs exactly once anywhere
    in the transcript is accepted (the agent usually only saw phrase times)."""
    toks = [norm_token(t) for t in target.split()]
    if not toks:
        return None
    n = len(toks)
    hits = [i for i in range(len(words) - n + 1)
            if all(norm_token(words[i + k].text) == toks[k] for k in range(n))]
    near = [i for i in hits if abs(words[i].start - at) <= window]
    if near:
        return min(near, key=lambda i: abs(words[i].start - at))
    return hits[0] if len(hits) == 1 else None


def resolve_edits(words: list[Word], fixes, emphasis) -> tuple[list[Word], set[int], list[str]]:
    """Apply caption fixes, then locate emphasis words in the fixed list. Returns (words, emphasised indices, notes
    about entries that matched nothing)."""
    out, notes = list(words), []
    for f in fixes:
        i = find_match(out, f.wrong, f.at)
        if i is None:
            notes.append(f"caption_fix '{f.wrong}' near {f.at:.2f}s matched no spoken words and was ignored")
            continue
        n = len(f.wrong.split())
        out[i:i + n] = [Word(f.right, out[i].start, out[i + n - 1].end)]
    emph: set[int] = set()
    for e in emphasis:
        i = find_match(out, e.word, e.at)
        if i is None:
            notes.append(f"emphasis '{e.word}' near {e.at:.2f}s matched no spoken words and was ignored")
            continue
        emph.update(range(i, i + len(e.word.split())))
    return out, emph, notes
