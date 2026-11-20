import { useEffect, useState } from "react";
import AgentFeed from "../components/AgentFeed";
import VideoPlayer from "../components/VideoPlayer";
import * as api from "../lib/api";
import type { FeedItem, ProjectDetail } from "../lib/types";

export default function Result({ detail, onRedo }: { detail: ProjectDetail; onRedo: (feedback: string) => void }) {
  const runs = detail.runs;
  const [sel, setSel] = useState(runs[runs.length - 1].n);
  const run = runs.find((r) => r.n === sel) ?? runs[runs.length - 1];
  const [feedback, setFeedback] = useState("");
  const [open, setOpen] = useState(false);
  const [feed, setFeed] = useState<FeedItem[] | null>(null);

  useEffect(() => { setSel(runs[runs.length - 1].n); }, [runs.length]);
  useEffect(() => { setFeed(null); setOpen(false); }, [run.n]);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && feed === null) {
      try { setFeed(await api.readRunFeed(detail.dir, run.n)); } catch { setFeed([]); }
    }
  }

  return (
    <div>
      <h1>{detail.title}</h1>
      {runs.length > 1 && (
        <div className="tabs">
          {runs.map((r) => (
            <button key={r.n} className={"tab" + (r.n === run.n ? " on" : "")} onClick={() => setSel(r.n)}>Lần {r.n}</button>
          ))}
        </div>
      )}
      <div className="pgrid">
        <VideoPlayer src={api.fileSrc(run.final)} />
        <div className="stack">
          {run.needsReview && <div className="flag">Video có thể cần xem lại: âm lượng hoặc độ dài chưa chuẩn</div>}
          {run.fallback && <div className="hint">AI không dựng được, đã cắt lặng tự động</div>}
          <div className="card">
            <h3>Đã làm gì</h3>
            <ul className="sum">{run.summary.map((s, i) => <li key={i}>{s}</li>)}</ul>
          </div>
          <div className="actions">
            <button className="btn dark" onClick={() => api.revealInFolder(run.final)}>Mở thư mục</button>
          </div>
          <div className="card">
            <div className="label">Muốn sửa gì?</div>
            <textarea value={feedback} onChange={(e) => setFeedback(e.target.value)}
              placeholder="Ví dụ: đưa giá lên đầu, cắt bớt đoạn cuối" />
            <div className="buildrow" style={{ marginTop: 12 }}>
              <button className="btn primary" disabled={!feedback.trim()}
                onClick={() => { onRedo(feedback.trim()); setFeedback(""); }}>Dựng lại</button>
            </div>
          </div>
          <div className="proc">
            <button onClick={toggle}>{open ? "▾" : "▸"} Xem quá trình AI</button>
            {open && (feed ? <AgentFeed items={feed} /> : <div className="hint">Đang tải…</div>)}
          </div>
        </div>
      </div>
    </div>
  );
}
