import { CalendarDays, Film, LayoutGrid, Plus, Settings } from "lucide-react";
import { useStore } from "../state/store";
import { nicheLabel } from "../lib/format";
import { recentProjects } from "../lib/library";
import type { ProjectStatus } from "../lib/types";
import { DeleteDialog, NameInput, ProjectMenu, useProjectActions } from "./ProjectActions";

const DOT: Record<ProjectStatus, string> = { new: "new", done: "done", needs_review: "review" };
const BUILDING = "run";

export default function Sidebar() {
  const { state, go, notify } = useStore();
  const actions = useProjectActions();
  const { renaming, setRenaming, rename } = actions;

  if (state.route.name === "onboarding") return null;
  const cur = state.route.name === "project" ? state.route.dir : null;
  const recent = recentProjects(state.projects, state.builds);
  const lib = state.route.name === "library";
  const sched = state.route.name === "schedule";
  const n = state.projects.length;
  return (
    <aside className="side" id="side">
      <div className="brand"><img className="logo" src="/app-icon.png" alt="" aria-hidden /><b>AutoEdit</b></div>
      <button className="newbtn" onClick={() => go({ name: "niche" })}><Plus size={17} strokeWidth={2.4} aria-hidden />Video mới</button>
      <div className="snav">
        <div className={"sn" + (lib ? " on" : "")} role="button" tabIndex={0}
          onClick={() => go({ name: "library" })} onKeyDown={(e) => { if (e.key === "Enter") go({ name: "library" }); }}>
          <LayoutGrid className="i" aria-hidden />Thư viện<span className="cnt">{n}</span></div>
        {state.hasSocialKey ? (
          <div className={"sn" + (sched ? " on" : "")} role="button" tabIndex={0}
            onClick={() => go({ name: "schedule" })} onKeyDown={(e) => { if (e.key === "Enter") go({ name: "schedule" }); }}><CalendarDays className="i" aria-hidden />Lịch đăng</div>
        ) : (
          <div className="sn off" aria-disabled="true" role="button" tabIndex={0} title="Nhập key bundle.social ở Cài đặt → Kết nối"
            onClick={() => notify("Nhập key bundle.social ở Cài đặt → Kết nối")}><CalendarDays className="i" aria-hidden />Lịch đăng</div>
        )}
      </div>
      {recent.length > 0 && <div className="slabel">Gần đây</div>}
      <div className="plist">
        {recent.map((p) => (
          <div key={p.dir} className={"pi" + (cur === p.dir ? " on" : "")} role="button" tabIndex={0}
            onClick={() => { if (renaming !== p.dir) go({ name: "project", dir: p.dir }); }}
            onKeyDown={(e) => { if (e.key === "Enter" && renaming !== p.dir) go({ name: "project", dir: p.dir }); }}>
            <span className="av"><Film aria-hidden /></span>
            <div className="tx">
              {renaming === p.dir
                ? <NameInput value={p.title} onDone={(v) => void rename(p, v)} onCancel={() => setRenaming(null)} />
                : <b>{p.title}</b>}
              <span>{state.builds[p.dir] ? "đang dựng…" : `${nicheLabel(p.niche)} · ${p.created}`}</span>
            </div>
            <ProjectMenu p={p} actions={actions} />
            <i className={"st " + (state.builds[p.dir] ? BUILDING : DOT[p.status])}
              data-status={state.builds[p.dir] ? "building" : p.status} />
          </div>
        ))}
        {n > recent.length && (
          <div className="seeall" role="button" tabIndex={0} onClick={() => go({ name: "library" })}
            onKeyDown={(e) => { if (e.key === "Enter") go({ name: "library" }); }}>Xem tất cả →</div>
        )}
      </div>
      <div className="sidefoot">
        <div className="ministat"><span>{n} video</span></div>
        <div className="pi" role="button" tabIndex={0} onClick={() => go({ name: "settings" })}>
          <Settings className="i" aria-hidden /><div className="tx"><b>Cài đặt</b></div>
        </div>
        <div className="copyright">Copyright © Build With Ai KhanhDev</div>
      </div>
      <DeleteDialog actions={actions} />
    </aside>
  );
}
