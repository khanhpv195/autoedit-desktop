import json
import math
import subprocess

import pytest

from autoedit.edl import CaptionFix, Emphasis, VoiceLine, validate_edl
from autoedit.prep import Prepared
from autoedit.prep.probe import probe
from autoedit.project import Project
from autoedit.render import compose as compose_mod
from autoedit.render.captions import Cue, TimedWord, build_voice_cues, write_ass
from autoedit.render.compose import compose
from autoedit.render.pipeline import render
from autoedit.render.qc import _pcm
from autoedit.transcript import Word
from autoedit.voice import eleven

WORDS = [Word("chào", 0.6, 1.0), Word("cả", 1.05, 1.3), Word("nhà", 1.35, 1.8),
         Word("giá", 3.2, 3.6), Word("189K", 3.7, 4.4)]
VO = {"enabled": True, "voice_id": "v1", "voice_name": "Mai"}
LINE = "Áo len xinh"
LINE_WORDS = [["Áo", 0.0, 0.3], ["len", 0.35, 0.6], ["xinh", 0.65, 0.95]]


def _put_voice(cache, text, words, freq=1000):
    cache.mkdir(parents=True, exist_ok=True)
    h = eleven.cache_key("v1", text)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=f={freq}:d=1:sample_rate=44100",
                    "-c:a", "libmp3lame", "-b:a", "128k", str(cache / f"{h}.mp3")], check=True)
    (cache / f"{h}.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def vo_setup(tmp_path, clip, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)     # any HTTP attempt would raise VoiceAuth
    d = tmp_path / "p"
    (d / "input").mkdir(parents=True)
    (d / "input" / "clip.mp4").write_bytes(clip.read_bytes())
    (d / "project.json").write_text(json.dumps({"niche": "chung", "clips": ["clip.mp4"], "voiceover": VO}))
    proj = Project.load(d)
    _put_voice(proj.work_dir / "vo", LINE, LINE_WORDS)
    prep = Prepared(info=probe(clip), normalized=proj.clip_paths[0], words=WORDS, keyframes=[])
    lines = {(2.0, LINE): VoiceLine(2.0, LINE, None, 1.0, [tuple(w) for w in LINE_WORDS])}
    edl, _ = validate_edl({"keep": [{"start": 0.0, "end": 5.0}], "voiceover": [{"at": 2.0, "text": LINE}],
                           "emphasis": [{"at": 2.4, "word": "len"}]},
                          WORDS, 6.0, voiceover_on=True, voice_lines=lines)
    return proj, prep, edl


def _rms(x, sr, a, b):
    seg = x[int(a * sr):int(b * sr)]
    return math.sqrt(sum(v * v for v in seg) / max(1, len(seg)))


def test_render_mutes_original_and_mixes_voice(vo_setup, tmp_path):
    proj, prep, edl = vo_setup
    res = render(prep, proj, edl, tmp_path / "out.mp4", preview=False)
    sr = 16000
    x = _pcm(res.path, sr)
    voice = _rms(x, sr, 2.1, 2.9)
    elsewhere = max(_rms(x, sr, 0.2, 1.8), _rms(x, sr, 3.3, 4.8))
    assert voice > 0.05 and voice > 20 * elsewhere, (voice, elsewhere)
    ass = (proj.work_dir / "render" / "captions.ass").read_text(encoding="utf-8")
    assert "ÁO {\\c&H0000D7FF&}LEN{\\c&H00FFFFFF&} XINH" in ass
    assert "CHÀO" not in ass and "189K" not in ass
    assert "Dialogue: 0,0:00:02.00," in ass


def test_build_voice_cues_offsets_fixes_and_emphasis():
    lines = [(1.5, 10.0, [("áo", 0.0, 0.3), ("len", 0.35, 0.6), ("giá", 0.7, 0.9), ("199k.", 0.95, 1.3)]),
             (4.0, 2.0, [("bấm", 0.0, 0.2), ("giỏ", 0.25, 0.5), ("hàng", 0.55, 0.8)])]
    cues = build_voice_cues(lines, [CaptionFix(10.0, "199k.", "199K.")], [Emphasis(10.7, "giá")], total=6.0)
    words = [w for c in cues for w in c.words]
    assert [w.text for w in words] == ["áo", "len", "giá", "199K.", "bấm", "giỏ", "hàng"]
    assert words[0].start == pytest.approx(1.5) and words[4].start == pytest.approx(4.0)
    assert next(w for w in words if w.text == "giá").emph
    assert all(a.end <= b.start + 1e-9 for a, b in zip(cues, cues[1:]))
    assert cues[-1].end == pytest.approx(5.95)


def test_compose_graph_mixes_voice_with_adelay(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(compose_mod.bins, "run", lambda cmd, **k: seen.update(cmd=cmd))
    ass = write_ass([Cue(0.2, 1.0, [TimedWord("a", 0.2, 1.0, 0.2, 0)])], tmp_path / "c.ass")
    compose(tmp_path / "b.mov", tmp_path / "o.mp4", duration=8.0, ass=ass, hook_png=None, logo_png=None,
            cta_png=None, music=tmp_path / "m.mp3", speech=[(1.25, 2.5)], duck_db=-14, preview=False,
            voice=[(tmp_path / "v0.mp3", 1.25), (tmp_path / "v1.mp3", 4.0)])
    cmd = seen["cmd"]
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "adelay=1250|1250" in graph and "adelay=4000|4000" in graph
    assert "amix=inputs=4:duration=first:normalize=0" in graph and "between(t,1.250,2.500)" in graph
    assert str(tmp_path / "v0.mp3") in cmd and str(tmp_path / "v1.mp3") in cmd


def test_voiceover_skips_pop_check_in_preview_and_final(vo_setup, tmp_path, monkeypatch):
    """With voiceover the base is muted and the voice runs across cuts: pop scores on the mix are meaningless."""
    from autoedit.render import pipeline
    from autoedit.render.qc import QcReport
    proj, prep, _ = vo_setup
    lines = {(2.0, LINE): VoiceLine(2.0, LINE, None, 1.0, [tuple(w) for w in LINE_WORDS])}
    edl, _ = validate_edl({"keep": [{"start": 0.0, "end": 2.5}, {"start": 3.0, "end": 5.0}],
                           "voiceover": [{"at": 2.0, "text": LINE}]},
                          WORDS, 6.0, voiceover_on=True, voice_lines=lines)
    seen = []
    monkeypatch.setattr(pipeline, "edit_checks",
                        lambda path, broll=(), cuts=(): seen.append(("pv", list(cuts))) or [])
    monkeypatch.setattr(pipeline, "run_qc",
                        lambda path, d, broll=(), cuts=(): seen.append(("qc", list(cuts))) or QcReport(ok=True))
    render(prep, proj, edl, tmp_path / "pv.mp4", preview=True)
    render(prep, proj, edl, tmp_path / "out.mp4", preview=False)
    assert seen == [("pv", []), ("qc", [])]
