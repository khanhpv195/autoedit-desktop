import json
from dataclasses import dataclass
from pathlib import Path

from autoedit import bins
from autoedit.errors import BadInput, RenderFailed

MAX_CLIP_SECONDS = 180
LOGO_EXT = {".png", ".jpg", ".jpeg"}
MUSIC_EXT = {".mp3", ".m4a", ".wav"}


@dataclass
class MediaInfo:
    duration: float
    width: int
    height: int
    fps: float
    hdr: bool
    has_audio: bool

    @property
    def portrait(self) -> bool:
        return self.height > self.width


def _fps(rate: str) -> float:
    num, _, den = rate.partition("/")
    return float(num) / float(den or 1) if float(den or 1) else 0.0


def probe(path: Path) -> MediaInfo:
    out = bins.run([bins.tool_path("ffprobe"), "-v", "error", "-print_format", "json",
                    "-show_format", "-show_streams", str(path)]).stdout
    data = json.loads(out)
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if v is None:
        raise BadInput("File không có hình")
    rotation = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    w, h = int(v["width"]), int(v["height"])
    if abs(rotation) % 180 == 90:
        w, h = h, w
    return MediaInfo(
        duration=float(data["format"].get("duration") or v.get("duration") or 0),
        width=w, height=h,
        fps=_fps(v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1"),
        hdr=v.get("color_transfer") in ("smpte2084", "arib-std-b67"),
        has_audio=any(s.get("codec_type") == "audio" for s in data["streams"]),
    )


def check_clip(path: Path) -> MediaInfo:
    try:
        info = probe(path)
    except RenderFailed as e:
        raise BadInput("Không đọc được file clip") from e
    if info.duration > MAX_CLIP_SECONDS:
        raise BadInput(f"Clip dài {info.duration:.0f}s, tối đa {MAX_CLIP_SECONDS}s")
    if info.duration <= 0:
        raise BadInput("Clip không có thời lượng")
    return info


def check_logo(path: Path) -> None:
    if path.suffix.lower() not in LOGO_EXT or not path.exists():
        raise BadInput("Logo phải là PNG hoặc JPG")


def check_music(path: Path) -> None:
    if path.suffix.lower() not in MUSIC_EXT or not path.exists():
        raise BadInput("Nhạc phải là MP3, M4A hoặc WAV")
