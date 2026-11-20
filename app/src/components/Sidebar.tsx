import { useStore } from "../state/store";
import { nicheLabel } from "../lib/format";
import type { ProjectStatus } from "../lib/types";

const DOT: Record<ProjectStatus, string> = { new: "new", done: "done", needs_review: "review" };
const BUILDING = "run";

export default function Sidebar() {
  const { state, go, notify } = useStore();
  if (state.route.name === "onboarding") return null;
  const cur = state.route.name === "project" ? state.route.dir : null;
  const n = state.projects.length;
  return (
    <aside className="side" id="side">
      <div className="brand"><div className="logo">▶</div><b>AutoEdit</b></div>
      <div className="snav">
        <div className={"sn" + (state.route.name === "schedule" ? "" : " on")} role="button" tabIndex={0}
          onClick={() => { if (state.route.name === "schedule") go({ name: "niche" }); }}>🎬 Video</div>
        {state.hasSocialKey ? (
          <div className={"sn" + (state.route.name === "schedule" ? " on" : "")} role="button" tabIndex={0}
            onClick={() => go({ name: "schedule" })} onKeyDown={(e) => { if (e.key === "Enter") go({ name: "schedule" }); }}>📅 Lịch đăng</div>
        ) : (
          <div className="sn off" aria-disabled="true" role="button" tabIndex={0} title="Nhập key bundle.social ở Cài đặt → Kết nối"
            onClick={() => notify("Nhập key bundle.social ở Cài đặt → Kết nối")}>📅 Lịch đăng</div>
        )}
      </div>
      <button className="newbtn" onClick={() => go({ name: "niche" })}>＋ Video mới</button>
      <div className="plist">
        {state.projects.map((p) => (
          <div key={p.dir} className={"pi" + (cur === p.dir ? " on" : "")} role="button" tabIndex={0}
            onClick={() => go({ name: "project", dir: p.dir })}
            onKeyDown={(e) => { if (e.key === "Enter") go({ name: "project", dir: p.dir }); }}>
            <div className="tx">
              <b>{p.title}</b>
              <span>{state.builds[p.dir] ? "đang dựng…" : `${nicheLabel(p.niche)} · ${p.created}`}</span>
            </div>
            <i className={"st " + (state.builds[p.dir] ? BUILDING : DOT[p.status])}
              data-status={state.builds[p.dir] ? "building" : p.status} />
          </div>
        ))}
      </div>
      <div className="sidefoot">
        <div className="ministat"><span>{n} video</span></div>
        <div className="pi" role="button" tabIndex={0} onClick={() => go({ name: "settings" })}>
          ⚙ <div className="tx"><b>Cài đặt</b></div>
        </div>
      </div>
    </aside>
  );
}
