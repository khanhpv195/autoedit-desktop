import os, stat
import pytest
from autoedit import bins
from autoedit.errors import RenderFailed


def test_env_bin_dir_wins(tmp_path, monkeypatch):
    fake = tmp_path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_text("#!/bin/sh\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("AUTOEDIT_BIN_DIR", str(tmp_path))
    assert bins.tool_path("ffmpeg") == str(fake)


def test_falls_back_to_path(monkeypatch):
    monkeypatch.delenv("AUTOEDIT_BIN_DIR", raising=False)
    assert bins.tool_path("ffprobe").endswith("ffprobe")


def test_missing_tool_raises(monkeypatch):
    monkeypatch.delenv("AUTOEDIT_BIN_DIR", raising=False)
    with pytest.raises(RenderFailed):
        bins.tool_path("definitely-not-a-tool-xyz")


def test_run_raises_with_stderr_tail():
    with pytest.raises(RenderFailed) as e:
        bins.run([bins.tool_path("ffmpeg"), "-v", "error", "-i", "/nope.mp4", "-f", "null", "-"])
    assert "nope.mp4" in e.value.message


def test_model_path_env(tmp_path, monkeypatch):
    m = tmp_path / "m.bin"; m.write_bytes(b"x")
    monkeypatch.setenv("AUTOEDIT_MODEL", str(m))
    assert bins.model_path() == m
