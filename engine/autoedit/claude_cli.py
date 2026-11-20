"""Download and locate the Claude Code CLI that matches the pinned claude-agent-sdk.

The CLI is not shipped in the installer: it is taken from the SDK's own PyPI wheel for this
platform, so its protocol always matches the SDK. Auto-update is disabled at call time
(see agent/options.py); upgrading means bumping SDK_VERSION + WHEELS and releasing the app.
"""
import hashlib
import os
import platform
import shutil
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path

from autoedit.bins import app_data_dir
from autoedit.errors import SetupRequired
from autoedit.events import Emitter

SDK_VERSION = "0.2.186"
_PY = "https://files.pythonhosted.org/packages"
WHEELS = {
    ("darwin", "arm64"): (
        f"{_PY}/e4/23/c4a6dc2ae62899dcd15e5ec54e9da65fc62a6f88a00b67620aa8096109a8/"
        "claude_agent_sdk-0.2.186-py3-none-macosx_11_0_arm64.whl",
        "4f98e05618a955fc49190465b4eb01cb3c2fca6e0b9319ee6e6c6dd042619bc6"),
    ("darwin", "x86_64"): (
        f"{_PY}/aa/99/67caf906962bd7d3ecbe767cd058bb604bec10430a9eeba8c8a073f05a39/"
        "claude_agent_sdk-0.2.186-py3-none-macosx_11_0_x86_64.whl",
        "0099f4701569b7a625ef7a9c097577cf203671b5f793fec1697192d21c0be6f5"),
    ("win32", "AMD64"): (
        f"{_PY}/b0/bb/27cd01b7a9771d0db926fced99b2b88e7b35d26f6c832dd3aba5e7e1f6a9/"
        "claude_agent_sdk-0.2.186-py3-none-win_amd64.whl",
        "b68eefc87a966ec94d1d7d51ee97c01cd9849b8cef9da2e00066086a091c2716"),
}
CHUNK = 1 << 20


def platform_key() -> tuple[str, str]:
    return sys.platform, platform.machine()


def _exe() -> str:
    return "claude.exe" if sys.platform == "win32" else "claude"


def member_name() -> str:
    return f"claude_agent_sdk/_bundled/{_exe()}"


def cli_file() -> Path:
    return app_data_dir() / "claude-cli" / SDK_VERSION / _exe()


def find_cli() -> Path | None:
    if env := os.environ.get("AUTOEDIT_CLAUDE_CLI"):
        return Path(env)
    if cli_file().exists():
        return cli_file()
    if not getattr(sys, "frozen", False):
        return None
    raise SetupRequired("Chưa tải Claude. Mở app để tải lại.")


def install_cli(events: Emitter, *, opener=urllib.request.urlopen) -> Path:
    target = cli_file()
    if target.exists():
        return target
    try:
        url, sha = WHEELS[platform_key()]
    except KeyError:
        raise SetupRequired(f"Máy này chưa được hỗ trợ ({platform_key()[0]} {platform_key()[1]})") from None
    target.parent.mkdir(parents=True, exist_ok=True)
    wheel = target.parent / "sdk.whl.part"
    digest = hashlib.sha256()
    try:
        with opener(url) as resp, open(wheel, "wb") as f:
            total, done = int(resp.headers.get("Content-Length") or 0), 0
            while chunk := resp.read(CHUNK):
                f.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if total and done % (16 * CHUNK) < CHUNK:
                    events.step(f"Đang tải Claude… {done * 100 // total}%", done / total)
        if digest.hexdigest() != sha:
            raise SetupRequired("File Claude tải về bị lỗi, thử lại")
        tmp = target.with_name(target.name + ".part")
        with zipfile.ZipFile(wheel) as z, z.open(member_name()) as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst, CHUNK)
        tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(tmp, target)
    except (OSError, KeyError, zipfile.BadZipFile) as e:
        raise SetupRequired(f"Không tải được Claude: {e}") from e
    finally:
        for leftover in target.parent.glob("*.part"):
            leftover.unlink()
    for old in target.parent.parent.iterdir():
        if old.is_dir() and old.name != SDK_VERSION:
            shutil.rmtree(old, ignore_errors=True)
    events.step("Đã tải Claude", 1.0)
    return target
