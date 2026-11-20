import subprocess
from pathlib import Path
import pytest


def _make(path: Path, w: int, h: int, dur: float, silent_from: float | None = None) -> Path:
    vol = f"volume='if(between(t,{silent_from},{silent_from + 1}),0,1)':eval=frame" if silent_from is not None else "anull"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r=30:d={dur}",
        "-f", "lavfi", "-i", f"sine=f=440:d={dur}",
        "-af", vol, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    ], check=True)
    return path


@pytest.fixture
def clip(tmp_path) -> Path:
    return _make(tmp_path / "clip.mp4", 1080, 1920, 6.0, silent_from=2.0)


@pytest.fixture
def landscape_clip(tmp_path) -> Path:
    return _make(tmp_path / "land.mp4", 1920, 1080, 4.0)


@pytest.fixture(autouse=True)
def _local_tz(monkeypatch):
    """Slots are local wall-clock time: pin the zone the tests are written in (UTC+7, no DST)."""
    import time
    monkeypatch.setenv("TZ", "Asia/Ho_Chi_Minh")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.fixture(autouse=True)
def _clean_secrets():
    from autoedit import secrets_env
    secrets_env.reset()
    yield
    secrets_env.reset()
