import io, json
from autoedit.events import Emitter

def lines(buf):
    return [json.loads(l) for l in buf.getvalue().splitlines()]

def test_each_event_is_one_json_line():
    buf = io.StringIO()
    e = Emitter(buf)
    e.step("Đang nghe lời thoại…", 0.2)
    e.agent("Bỏ đoạn vấp", tool="set_edl")
    e.preview("/p/preview.mp4", 1)
    e.done("/p/final.mp4", ["a"], {"turns": 3}, False)
    e.error("RATE_LIMIT", "hết lượt", retry_at="2026-11-20T14:30:00+07:00")
    out = lines(buf)
    assert [o["type"] for o in out] == ["step", "agent", "preview", "done", "error"]
    assert out[0] == {"type": "step", "label": "Đang nghe lời thoại…", "progress": 0.2}
    assert out[1] == {"type": "agent", "text": "Bỏ đoạn vấp", "tool": "set_edl"}
    assert out[3]["needs_review"] is False
    assert out[4]["retry_at"].endswith("+07:00")

def test_non_ascii_is_kept_readable():
    buf = io.StringIO()
    Emitter(buf).step("Đang dựng", 0.5)
    assert "Đang dựng" in buf.getvalue()

def test_progress_is_clamped():
    buf = io.StringIO()
    Emitter(buf).step("x", 1.7)
    assert lines(buf)[0]["progress"] == 1.0
