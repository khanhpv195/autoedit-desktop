"""JSON-lines events on stdout. The Tauri app reads one object per line."""
import json
import sys
from typing import TextIO


class Emitter:
    def __init__(self, stream: TextIO | None = None):
        self.stream = stream or sys.stdout

    def _emit(self, obj: dict) -> None:
        self.stream.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.stream.flush()

    def step(self, label: str, progress: float) -> None:
        self._emit({"type": "step", "label": label, "progress": round(min(1.0, max(0.0, progress)), 3)})

    def agent(self, text: str, tool: str | None = None) -> None:
        self._emit({"type": "agent", "text": text, "tool": tool})

    def preview(self, path: str, round: int) -> None:
        self._emit({"type": "preview", "path": path, "round": round})

    def done(self, final: str, summary: list[str], usage: dict, needs_review: bool) -> None:
        self._emit({"type": "done", "final": final, "summary": summary, "usage": usage,
                    "needs_review": needs_review})

    def error(self, code: str, message: str, retry_at: str | None = None) -> None:
        self._emit({"type": "error", "code": code, "message": message, "retry_at": retry_at})
    def cards(self, cards: list[dict]) -> None:
        self._emit({"type": "cards", "cards": cards})

    def auth(self, source: str) -> None:
        self._emit({"type": "auth", "source": source})

    def setup(self, claude_cli: str) -> None:
        self._emit({"type": "setup", "claude_cli": claude_cli})
