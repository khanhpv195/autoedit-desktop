import subprocess
import pytest
from autoedit.render.look import look_graph, LOOKS
from autoedit.project import NICHES


def test_every_niche_has_a_look():
    assert set(LOOKS) == set(NICHES)


@pytest.mark.parametrize("niche", ["my-pham", "phu-kien", "chung", "thoi-trang"])
def test_colour_preserved(niche):
    g = look_graph(niche, "0:v", "v")
    assert "saturation=1.0" in g and "colorbalance" not in g and "hue" not in g


def test_food_gets_saturation_boost():
    assert "saturation=1.06" in look_graph("do-an", "0:v", "v")


def test_skin_only_for_fashion():
    assert "bilateral" in look_graph("thoi-trang", "0:v", "v")
    assert all("bilateral" not in look_graph(n, "0:v", "v") for n in NICHES if n != "thoi-trang")


def test_scale_appended():
    g = look_graph("chung", "0:v", "v", scale="540:960")
    assert g.endswith("scale=540:960,format=yuv420p[v]")


@pytest.mark.parametrize("niche", ["thoi-trang", "do-an"])
def test_graph_runs_in_ffmpeg(niche, clip, tmp_path):
    out = tmp_path / "f.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-filter_complex",
                    look_graph(niche, "0:v", "v"), "-map", "[v]", "-frames:v", "1", str(out)], check=True)
    assert out.stat().st_size > 1000
