import json
import os
import subprocess
import pytest
import autoedit.prep as prep_mod
from autoedit import bins
from autoedit.errors import RenderFailed
from autoedit.fsutil import atomic_write_text
from autoedit.prep.normalize import normalize
from autoedit.prep.probe import probe
from autoedit.project import Project


def test_atomic_write_replaces_and_leaves_no_temp(tmp_path):
    f = tmp_path / "a.json"
    atomic_write_text(f, "one")
    atomic_write_text(f, "two")
    assert f.read_text() == "two" and [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_atomic_write_failure_keeps_old_file(tmp_path, monkeypatch):
    f = tmp_path / "a.json"
    f.write_text("old")
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("killed")))
    with pytest.raises(OSError):
        atomic_write_text(f, "new")
    monkeypatch.undo()
    assert f.read_text() == "old" and [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_project_save_is_atomic(tmp_path, monkeypatch):
    (tmp_path / "input").mkdir()
    (tmp_path / "input" / "c.mp4").write_bytes(b"x")
    (tmp_path / "project.json").write_text(json.dumps({"niche": "chung", "clip": "c.mp4", "runs": [{"n": 1}]}))
    p = Project.load(tmp_path)
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("killed")))
    with pytest.raises(OSError):
        p.save()
    monkeypatch.undo()
    assert json.loads((tmp_path / "project.json").read_text())["runs"] == [{"n": 1}]


def test_killed_normalize_leaves_no_destination(clip, tmp_path, monkeypatch):
    info = probe(clip)
    def dying(cmd, *a, **k):
        with open(cmd[-1], "wb") as f:
            f.write(b"truncated")
        raise RenderFailed("killed")
    monkeypatch.setattr(bins, "run", dying)
    dst = tmp_path / "normalized.mp4"
    with pytest.raises(RenderFailed):
        normalize(clip, dst, info)
    assert not dst.exists()


def _project(tmp_path, clip):
    d = tmp_path / "proj"; (d / "input").mkdir(parents=True)
    (d / "input" / "clip.mp4").write_bytes(clip.read_bytes())
    (d / "project.json").write_text(json.dumps({"niche": "chung", "clip": "clip.mp4"}))
    return d


def test_truncated_normalized_cache_is_not_reused(clip, tmp_path, monkeypatch):
    from autoedit.events import Emitter
    import io
    from autoedit.transcript import Word
    d = _project(tmp_path, clip)
    monkeypatch.setattr(prep_mod, "transcribe", lambda v, wd: [Word("a", 0.1, 0.4)])
    p = prep_mod.prepare(Project.load(d), Emitter(io.StringIO()))
    good = p.normalized.read_bytes()
    p.normalized.write_bytes(good[: len(good) // 3])      # a kill mid-write, mtime newer than the clip
    p2 = prep_mod.prepare(Project.load(d), Emitter(io.StringIO()))
    assert p2.normalized.stat().st_size > len(good) // 2      # re-normalized, not the 1/3 file (its moov atom still says 6 s)


def test_corrupt_transcript_cache_is_recomputed(clip, tmp_path, monkeypatch):
    import importlib
    tr = importlib.import_module("autoedit.prep.transcribe")
    from autoedit.transcript import Word
    monkeypatch.setattr(tr, "_run_whisper", lambda *a: [Word("x", 1.0, 1.2)])
    (tmp_path / "transcript.json").write_text('{"sha256": "abc", "wor')
    assert tr.transcribe(clip, tmp_path) == [Word("x", 1.0, 1.2)]
    assert json.loads((tmp_path / "transcript.json").read_text())["words"]
