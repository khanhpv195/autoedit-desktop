"""Locate bundled resources in dev (repo) and frozen (PyInstaller) mode."""
import os
import sys
from pathlib import Path


def _base() -> Path:
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    return Path(__file__).resolve().parents[2]  # repo root (engine/autoedit/.. /..)


def agent_dir() -> Path:
    if env := os.environ.get("AUTOEDIT_AGENT_DIR"):
        return Path(env)
    return _base() / "agent"


def assets_dir() -> Path:
    if env := os.environ.get("AUTOEDIT_ASSETS_DIR"):
        return Path(env)
    frozen = getattr(sys, "_MEIPASS", None)
    return Path(frozen) / "assets" if frozen else Path(__file__).resolve().parents[1] / "assets"
