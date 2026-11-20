import hashlib, io, sys, zipfile
import pytest
from autoedit import claude_cli as cc
from autoedit.errors import SetupRequired
from autoedit.events import Emitter


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "app_data_dir", lambda: tmp_path)
    monkeypatch.delenv("AUTOEDIT_CLAUDE_CLI", raising=False)
    return tmp_path


def fake_wheel(member: str, payload: bytes = b"#!/bin/sh\necho 2.1.329\n") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("claude_agent_sdk/__init__.py", "")
        z.writestr(member, payload)
    return buf.getvalue()


class Resp(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}
    def __enter__(self):
        return self
    def __exit__(self, *a):
        self.close()


def setup_wheel(monkeypatch, data: bytes, sha: str | None = None):
    key = cc.platform_key()
    monkeypatch.setitem(cc.WHEELS, key, ("https://example/sdk.whl", sha or hashlib.sha256(data).hexdigest()))
    calls = []
    def opener(url):
        calls.append(url)
        return Resp(data)
    return opener, calls


def test_install_extracts_executable(data_dir, monkeypatch):
    opener, calls = setup_wheel(monkeypatch, fake_wheel(cc.member_name()))
    out = io.StringIO()
    path = cc.install_cli(Emitter(out), opener=opener)
    assert path == cc.cli_file() and path.read_bytes().startswith(b"#!/bin/sh")
    if sys.platform != "win32":
        assert path.stat().st_mode & 0o111
    assert calls == ["https://example/sdk.whl"] and "Đang tải Claude" in out.getvalue()
    assert not list(path.parent.glob("*.part"))
    cc.install_cli(Emitter(io.StringIO()), opener=opener)   # second call: no download
    assert len(calls) == 1


def test_bad_checksum_leaves_nothing(data_dir, monkeypatch):
    opener, _ = setup_wheel(monkeypatch, fake_wheel(cc.member_name()), sha="0" * 64)
    with pytest.raises(SetupRequired):
        cc.install_cli(Emitter(io.StringIO()), opener=opener)
    assert not cc.cli_file().exists() and not list(cc.cli_file().parent.glob("*"))


def test_removes_old_versions(data_dir, monkeypatch):
    old = data_dir / "claude-cli" / "0.1.0"; old.mkdir(parents=True); (old / "claude").write_text("x")
    opener, _ = setup_wheel(monkeypatch, fake_wheel(cc.member_name()))
    cc.install_cli(Emitter(io.StringIO()), opener=opener)
    assert not old.exists()


def test_unsupported_platform(data_dir, monkeypatch):
    monkeypatch.setattr(cc, "platform_key", lambda: ("sunos5", "sparc"))
    with pytest.raises(SetupRequired):
        cc.install_cli(Emitter(io.StringIO()))


def test_find_cli_order(data_dir, monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert cc.find_cli() is None                       # dev: SDK uses its own copy
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with pytest.raises(SetupRequired):
        cc.find_cli()
    cc.cli_file().parent.mkdir(parents=True); cc.cli_file().write_text("x")
    assert cc.find_cli() == cc.cli_file()
    other = tmp_path / "my-claude"; other.write_text("x")
    monkeypatch.setenv("AUTOEDIT_CLAUDE_CLI", str(other))
    assert cc.find_cli() == other


def test_pinned_wheels_cover_targets():
    assert set(cc.WHEELS) >= {("darwin", "arm64"), ("darwin", "x86_64"), ("win32", "AMD64")}
    for url, sha in cc.WHEELS.values():
        assert f"claude_agent_sdk-{cc.SDK_VERSION}-" in url and len(sha) == 64


@pytest.mark.slow
def test_real_download_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "app_data_dir", lambda: tmp_path)
    import subprocess
    path = cc.install_cli(Emitter(io.StringIO()))
    assert "2.1.329" in subprocess.run([str(path), "--version"], capture_output=True, text=True).stdout
