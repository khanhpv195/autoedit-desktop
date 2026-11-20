import json, subprocess
from autoedit.edl import Range
from autoedit.prep.probe import probe
from autoedit.render.segments import render_base


def acodec(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name",
                          "-of", "json", str(p)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]["codec_name"]


def test_base_duration_and_pcm(clip, tmp_path):
    base = render_base(clip, [Range(3.5, 5.0), Range(0.5, 1.5)], "chung", tmp_path, preview=False)
    i = probe(base)
    assert abs(i.duration - 2.5) < 0.1 and (i.width, i.height) == (1080, 1920)
    assert acodec(base) == "pcm_s16le"


def test_preview_is_540p(clip, tmp_path):
    base = render_base(clip, [Range(0.5, 1.5)], "thoi-trang", tmp_path, preview=True)
    assert (probe(base).width, probe(base).height) == (540, 960)
