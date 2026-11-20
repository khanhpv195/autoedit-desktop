"""Find sidecar binaries (bundled by Tauri next to the engine) and run them."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from autoedit.errors import RenderFailed

MODEL_NAME = "ggml-large-v3-turbo.bin"


def tool_path(name: str) -> str:
    exe = name + (".exe" if os.name == "nt" else "")
    if d := os.environ.get("AUTOEDIT_BIN_DIR"):
        p = Path(d) / exe
        if p.exists():
            return str(p)
    # Frozen: sidecars sit next to the engine executable.
    if getattr(sys, "frozen", False):
        p = Path(sys.executable).parent / exe
        if p.exists():
            return str(p)
    found = shutil.which(name)
    if not found:
        raise RenderFailed(f"Không tìm thấy công cụ {name}")
    return found


def app_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AutoEdit"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home())) / "AutoEdit"
    return Path.home() / ".local" / "share" / "AutoEdit"


def model_path() -> Path:
    if env := os.environ.get("AUTOEDIT_MODEL"):
        return Path(env)
    return app_data_dir() / "models" / MODEL_NAME


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-20:])
        raise RenderFailed(f"{Path(cmd[0]).name} lỗi (mã {proc.returncode}):\n{tail}")
    return proc
