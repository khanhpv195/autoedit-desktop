import { ChevronRight, FolderOpen, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import AgentFeed from "../components/AgentFeed";
import PostCard from "../components/PostCard";
import VideoPlayer from "../components/VideoPlayer";
import * as api from "../lib/api";
import type { FeedItem, ProjectDetail } from "../lib/types";

export default function Result({ detail, onRedo, onPosted }: { detail: ProjectDetail; onRedo: (feedback: string) => void; onPosted?: () => void }) {
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
      <div className="phead">
        <h1>{detail.title}</h1>
        <button className="btn ghost" onClick={() => api.revealInFolder(run.final)}><FolderOpen size={16} aria-hidden />Mở thư mục</button>
      </div>
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
          <PostCard key={run.n} detail={detail} run={run} onPosted={onPosted} />
          <div className="card">
            <div className="label">Muốn sửa gì?</div>
            <textarea value={feedback} onChange={(e) => setFeedback(e.target.value)}
              placeholder="Ví dụ: đưa giá lên đầu, cắt bớt đoạn cuối" />
            <div className="buildrow" style={{ marginTop: 12, justifyContent: "flex-end" }}>
              <button className="btn primary" disabled={!feedback.trim()}
                onClick={() => { onRedo(feedback.trim()); setFeedback(""); }}><RotateCcw size={16} aria-hidden />Dựng lại</button>
            </div>
          </div>
          <div className="proc">
            <button onClick={toggle} aria-expanded={open}><ChevronRight size={16} aria-hidden style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform .15s" }} />Xem quá trình AI</button>
            {open && (feed ? <AgentFeed items={feed} /> : <div className="hint">Đang tải…</div>)}
          </div>
        </div>
      </div>
    </div>
  );
}
