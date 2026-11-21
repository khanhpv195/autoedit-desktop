import json

from autoedit import bins
from autoedit.errors import VoiceFailed


def audio_duration(path) -> float:
    """Seconds of audio in a voiceover file (ffprobe)."""
    try:
        out = bins.run([bins.tool_path("ffprobe"), "-v", "error", "-print_format", "json", "-show_format",
                        str(path)]).stdout
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        raise VoiceFailed("Không đọc được file lồng tiếng") from None
