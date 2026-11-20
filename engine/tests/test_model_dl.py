import hashlib, io
import pytest
from autoedit import model_dl
from autoedit.errors import SetupRequired
from autoedit.events import Emitter

DATA = b"x" * 5000

class Resp(io.BytesIO):
    def __init__(self, body, status=200, length=None):
        super().__init__(body); self.status = status
        self.headers = {"Content-Length": str(len(body) if length is None else length)}
    def __enter__(self): return self
    def __exit__(self, *a): self.close()

def patch_consts(monkeypatch, data=DATA):
    monkeypatch.setattr(model_dl, "MODEL_SIZE", len(data))
    monkeypatch.setattr(model_dl, "MODEL_SHA256", hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(model_dl, "CHUNK", 1000)

def test_fresh_download(tmp_path, monkeypatch):
    patch_consts(monkeypatch)
    out = io.StringIO()
    p = model_dl.install_model(Emitter(out), opener=lambda req: Resp(DATA), target=tmp_path / "m.bin")
    assert p.read_bytes() == DATA and not (tmp_path / "m.bin.part").exists()
    assert '"progress": 1.0' in out.getvalue()

def test_resume_uses_range(tmp_path, monkeypatch):
    patch_consts(monkeypatch)
    (tmp_path / "m.bin.part").write_bytes(DATA[:2000])
    seen = {}
    def opener(req):
        seen["range"] = req.get_header("Range")
        return Resp(DATA[2000:], status=206)
    p = model_dl.install_model(Emitter(io.StringIO()), opener=opener, target=tmp_path / "m.bin")
    assert seen["range"] == "bytes=2000-" and p.read_bytes() == DATA

def test_server_ignores_range_restarts(tmp_path, monkeypatch):
    patch_consts(monkeypatch)
    (tmp_path / "m.bin.part").write_bytes(b"junk")
    p = model_dl.install_model(Emitter(io.StringIO()), opener=lambda req: Resp(DATA, status=200), target=tmp_path / "m.bin")
    assert p.read_bytes() == DATA

def test_bad_hash_deletes_part(tmp_path, monkeypatch):
    patch_consts(monkeypatch)
    with pytest.raises(SetupRequired):
        model_dl.install_model(Emitter(io.StringIO()), opener=lambda req: Resp(b"y" * 5000), target=tmp_path / "m.bin")
    assert not (tmp_path / "m.bin.part").exists() and not (tmp_path / "m.bin").exists()

def test_network_error_keeps_part(tmp_path, monkeypatch):
    patch_consts(monkeypatch)
    class Broken(Resp):
        def read(self, n=-1):
            if self.tell() >= 1000: raise OSError("reset")
            return super().read(n)
    with pytest.raises(SetupRequired):
        model_dl.install_model(Emitter(io.StringIO()), opener=lambda req: Broken(DATA), target=tmp_path / "m.bin")
    assert (tmp_path / "m.bin.part").stat().st_size == 1000

def test_existing_full_size_skips(tmp_path, monkeypatch):
    patch_consts(monkeypatch)
    (tmp_path / "m.bin").write_bytes(DATA)
    p = model_dl.install_model(Emitter(io.StringIO()), opener=lambda req: pytest.fail("no download"), target=tmp_path / "m.bin")
    assert p == tmp_path / "m.bin"

def test_cli_setup_model_emits_model(monkeypatch, tmp_path, capsys):
    from autoedit import cli
    monkeypatch.setattr(cli, "install_model", lambda events: tmp_path / "m.bin")
    assert cli.main(["setup-model"]) == 0
    assert '{"type": "model", "path": "' in capsys.readouterr().out


def test_complete_part_goes_straight_to_hashing(tmp_path, monkeypatch):
    patch_consts(monkeypatch)
    (tmp_path / "m.bin.part").write_bytes(DATA)
    p = model_dl.install_model(Emitter(io.StringIO()), opener=lambda req: pytest.fail("no request"), target=tmp_path / "m.bin")
    assert p.read_bytes() == DATA and not (tmp_path / "m.bin.part").exists()



def test_http_416_restarts_from_scratch(tmp_path, monkeypatch):
    import urllib.error
    patch_consts(monkeypatch)
    (tmp_path / "m.bin.part").write_bytes(DATA[:2000])
    calls = []
    def opener(req):
        calls.append(req.get_header("Range"))
        if req.get_header("Range"):
            raise urllib.error.HTTPError(req.full_url, 416, "Range Not Satisfiable", {}, None)
        return Resp(DATA)
    p = model_dl.install_model(Emitter(io.StringIO()), opener=opener, target=tmp_path / "m.bin")
    assert p.read_bytes() == DATA and calls == ["bytes=2000-", None]


def test_oversized_part_is_discarded(tmp_path, monkeypatch):
    patch_consts(monkeypatch)
    (tmp_path / "m.bin.part").write_bytes(b"z" * 6000)
    p = model_dl.install_model(Emitter(io.StringIO()), opener=lambda req: Resp(DATA), target=tmp_path / "m.bin")
    assert p.read_bytes() == DATA
