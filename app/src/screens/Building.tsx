import AgentFeed from "../components/AgentFeed";
import ProgressSteps from "../components/ProgressSteps";
import VideoPlayer from "../components/VideoPlayer";
import * as api from "../lib/api";
import type { FeedItem } from "../lib/types";

export type BuildState = {
  progress: number;
  label: string;
  items: FeedItem[];
  preview: { path: string; round: number } | null;
};

export default function Building({ build, onCancel }: { build: BuildState; onCancel: () => void }) {
  return (
    <div>
      <h1>Đang dựng…</h1>
      <div className="sub">Xong sẽ tự hiện video. Có thể mất vài phút.</div>
      <div className="agrid">
        <div className="stack">
          <div className="card">
            <ProgressSteps progress={build.progress} label={build.label} />
            <div className="bar" style={{ marginTop: 8 }}><i style={{ width: Math.round(build.progress * 100) + "%" }} /></div>
          </div>
          {build.preview && (
            <div className="card">
              <h3>Bản xem nhanh vòng {build.preview.round}</h3>
              <VideoPlayer small src={api.fileSrc(build.preview.path)} />
            </div>
          )}
          <button className="btn ghost" onClick={onCancel}>Hủy</button>
        </div>
        <AgentFeed items={build.items} />
      </div>
    </div>
  );
}
