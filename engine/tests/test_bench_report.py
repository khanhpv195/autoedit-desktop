from pathlib import Path
from bench_path import run_bench


def test_report_html(tmp_path):
    results = [{"name": "my-pham-1", "niche": "my-pham", "status": "done", "duration": 24.3,
                "needs_review": False, "fallback": False, "summary": ["Bỏ đoạn lặng"], "thumbs": []},
               {"name": "do-an-2", "niche": "do-an", "status": "error", "error": "RATE_LIMIT", "thumbs": []}]
    html = run_bench.build_report(results, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "my-pham-1" in html and "Bỏ đoạn lặng" in html and "RATE_LIMIT" in html
    assert html.count("<tr") == 3
