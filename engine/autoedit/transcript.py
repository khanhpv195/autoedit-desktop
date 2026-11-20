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


def speech_duration(words: list[Word]) -> float:
    return sum(p.end - p.start for p in pack_phrases(words))


def words_to_json(words: list[Word]) -> list[dict]:
    return [{"text": w.text, "start": w.start, "end": w.end} for w in words]


def words_from_json(data: list[dict]) -> list[Word]:
    return [Word(d["text"], float(d["start"]), float(d["end"])) for d in data]
