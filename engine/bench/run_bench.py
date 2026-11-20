"""Run every clip in bench/clips through `autoedit edit` and write bench/out/report.html."""
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
CLIPS, OUT = ROOT / "clips", ROOT / "out"


def _thumbs(video: Path, out_dir: Path, duration: float) -> list[str]:
    paths = []
    for i, t in enumerate((0.5, duration / 2, max(0.0, duration - 1))):
        p = out_dir / f"t{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=180:-2", str(p)], check=False)
        if p.exists():
            paths.append(p.relative_to(OUT).as_posix())
    return paths


def run_one(src: Path) -> dict:
    name, niche = src.name, src.name.rsplit("-", 1)[0]
    proj = OUT / name
    shutil.rmtree(proj, ignore_errors=True)
    (proj / "input").mkdir(parents=True)
    data = {"niche": niche, "clip": "clip.mp4"}
    shutil.copy(src / "clip.mp4", proj / "input" / "clip.mp4")
    for key, fname in (("logo", "logo.png"), ("music", "music.mp3")):
        if (src / fname).exists():
            shutil.copy(src / fname, proj / "input" / fname)
            data[key] = fname
    (proj / "project.json").write_text(json.dumps(data), encoding="utf-8")
    prompt = (src / "prompt.txt").read_text(encoding="utf-8").strip() if (src / "prompt.txt").exists() else ""
    proc = subprocess.run([sys.executable, "-m", "autoedit", "edit", "--project", str(proj), "--prompt", prompt],
                          capture_output=True, text=True)
    events = [json.loads(l) for l in proc.stdout.splitlines() if l.startswith("{")]
    last = events[-1] if events else {"type": "error", "code": "NO_OUTPUT", "message": proc.stderr[-500:]}
    if last["type"] != "done":
        return {"name": name, "niche": niche, "status": "error", "error": last.get("code"), "thumbs": []}
    final = Path(last["final"])
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(final)], capture_output=True, text=True).stdout or 0)
    return {"name": name, "niche": niche, "status": "done", "duration": round(dur, 1),
            "needs_review": last["needs_review"], "fallback": last["usage"].get("fallback", False),
            "summary": last["summary"], "thumbs": _thumbs(final, proj, dur)}


def build_report(results: list[dict], out: Path) -> Path:
    rows = ["<tr><th>Clip</th><th>Ngành</th><th>Kết quả</th><th>Thời lượng</th><th>QC</th><th>Dự phòng</th>"
            "<th>AI đã làm</th><th>Ảnh</th></tr>"]
    for r in results:
        ok = r["status"] == "done"
        imgs = "".join(f'<img src="{html.escape(t)}" height="160">' for t in r.get("thumbs", []))
        rows.append(
            f"<tr><td>{html.escape(r['name'])}</td><td>{r['niche']}</td>"
            f"<td>{'xong' if ok else html.escape(str(r.get('error')))}</td>"
            f"<td>{r.get('duration', '')}</td><td>{'⚠️' if r.get('needs_review') else ('✓' if ok else '')}</td>"
            f"<td>{'có' if r.get('fallback') else ''}</td>"
            f"<td>{'<br>'.join(html.escape(s) for s in r.get('summary', []))}</td><td>{imgs}</td></tr>")
    out.write_text("<meta charset='utf-8'><style>td,th{border:1px solid #ccc;padding:6px;vertical-align:top}"
                   "table{border-collapse:collapse;font:13px sans-serif}</style><table>" + "".join(rows) + "</table>",
                   encoding="utf-8")
    return out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    clips = sorted(p for p in CLIPS.iterdir() if (p / "clip.mp4").exists())
    results = []
    for c in clips:
        print(f"→ {c.name}", flush=True)
        results.append(run_one(c))
    print(build_report(results, OUT / "report.html"))


if __name__ == "__main__":
    main()
