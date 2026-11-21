"""Secrets the app hands us through the environment.

The app sets BUNDLE_SOCIAL_KEY (for `social …` commands), AUTOEDIT_MCP (for `edit` and `mcp-check`) and
ELEVENLABS_API_KEY (for `edit`, only when voiceover is used).
`scrub()` reads them once and removes them from os.environ, so no child process we start afterwards
(Claude CLI, customer MCP servers the CLI spawns, ffmpeg) inherits them. Code asks `get()` instead of
os.environ; it falls back to os.environ so unit tests that monkeypatch the environment still work.
"""
import os

SECRET_NAMES = ("BUNDLE_SOCIAL_KEY", "AUTOEDIT_MCP", "ELEVENLABS_API_KEY")
_stash: dict[str, str] = {}


def scrub() -> None:
    for name in SECRET_NAMES:
        value = os.environ.pop(name, None)
        if value is not None:
            _stash[name] = value


def get(name: str) -> str | None:
    return _stash.get(name) or os.environ.get(name)


def reset() -> None:
    """Tests only."""
    _stash.clear()
