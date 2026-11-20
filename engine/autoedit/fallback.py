from autoedit.edl import Edl, Range, validate_edl
from autoedit.transcript import Word, pack_phrases

FALLBACK_SUMMARY = "AI không dựng được lần này — đã tự cắt các khoảng lặng, không có hook."


def silence_cut_edl(words: list[Word], clip_duration: float) -> Edl:
    if not words:
        return Edl(keep=[Range(0.0, clip_duration, "whole clip")])
    keep = [{"start": p.start, "end": p.end, "reason": "speech"} for p in pack_phrases(words, gap=0.6)]
    edl, _ = validate_edl({"keep": keep}, words, clip_duration)
    return edl
