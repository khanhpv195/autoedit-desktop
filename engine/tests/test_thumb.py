import json
from pathlib import Path

from autoedit import cli
from autoedit.render import thumb as thumb_mod
from autoedit.render.thumb import backfill, make_thumb
from tests.conftest import _make


def test_make_thumb_writes_jpeg(clip, tmp_path):
    out = tmp_path / "thumb.jpg"
    assert make_thumb(clip, out) is True
    assert out.read_bytes()[:2] == b"\xff\xd8"
    assert not list(tmp_path.glob("*.part*"))


def test_make_thumb_short_clip(tmp_path):
    short = _make(tmp_path / "short.mp4", 360, 640, 0.5)
    out = tmp_path / "thumb.jpg"
    assert make_thumb(short, out) is True and out.stat().st_size > 0


def test_make_thumb_bad_input_returns_false(tmp_path):
    bad = tmp_path / "bad.mp4"; bad.write_bytes(b"not a video")
    out = tmp_path / "thumb.jpg"
    assert make_thumb(bad, out) is False
    assert not out.exists()
    assert make_thumb(tmp_path / "missing.mp4", out) is False


def _project(root: Path, name: str, runs: list[int], clip: Path | None) -> Path:
    d = root / name; d.mkdir(parents=True)
    (d / "project.json").write_text(json.dumps({"niche": "chung", "runs": [{"n": n} for n in runs]}))
    for n in runs:
        (d / "runs" / str(n)).mkdir(parents=True)
        if clip is not None:
            (d / "runs" / str(n) / "final.mp4").write_bytes(clip.read_bytes())
    return d


def test_backfill_makes_only_missing_last_run_thumbs(clip, tmp_path):
    root = tmp_path / "projects"
    a = _project(root, "a", [1, 2], clip)
    b = _project(root, "b", [1], clip); (b / "runs" / "1" / "thumb.jpg").write_bytes(b"x")
    _project(root, "c", [], None)
    _project(root, "d", [1], None)                       # run without final.mp4
    (root / "e").mkdir(); (root / "e" / "project.json").write_text("{broken")
    made: list[Path] = []
    assert backfill(root, made.append) == 1
    assert made == [a]
    assert (a / "runs" / "2" / "thumb.jpg").exists() and not (a / "runs" / "1" / "thumb.jpg").exists()
    assert (b / "runs" / "1" / "thumb.jpg").read_bytes() == b"x"


def test_backfill_missing_root(tmp_path):
    assert backfill(tmp_path / "nope", lambda d: None) == 0


def test_thumbs_command_events(clip, tmp_path, capsys):
    root = tmp_path / "projects"
    a = _project(root, "a", [1], clip)
    assert cli.main(["thumbs", "--root", str(root)]) == 0
    ev = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    assert ev == [{"type": "thumb", "dir": str(a)}, {"type": "thumbs_done", "made": 1}]
