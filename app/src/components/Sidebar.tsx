import { useEffect, useRef, useState } from "react";
import { CalendarDays, Clapperboard, Film, MoreHorizontal, Play, Plus, Settings } from "lucide-react";
import { useStore } from "../state/store";
import * as api from "../lib/api";
import { toEngineError } from "../lib/errors";
import { nicheLabel } from "../lib/format";
import { MAX_NAME } from "../lib/defaults";
import type { ProjectStatus, ProjectSummary } from "../lib/types";

const DOT: Record<ProjectStatus, string> = { new: "new", done: "done", needs_review: "review" };
const BUILDING = "run";

export default function Sidebar() {
  const { state, go, notify, refreshProjects } = useStore();
  const [menu, setMenu] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null);
  const [busy, setBusy] = useState(false);

  // A click anywhere else closes the ⋯ menu.
  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [menu]);

  if (state.route.name === "onboarding") return null;
  const cur = state.route.name === "project" ? state.route.dir : null;
  const openDir = state.route.name === "project" || state.route.name === "new" ? state.route.dir ?? null : null;

  async function rename(p: ProjectSummary, name: string) {
    setRenaming(null);
    if (name.trim() === p.title) return;
    try { await api.renameProject(p.dir, name); await refreshProjects(); }
    catch (e) { notify(toEngineError(e).message); }
  }

  async function remove(p: ProjectSummary) {
    setBusy(true);
    try {
      await api.deleteProject(p.dir);
      setDeleting(null);
      if (openDir === p.dir) go({ name: "niche" });
      await refreshProjects();
      notify(`Đã xoá “${p.title}”`);
    } catch (e) { notify(toEngineError(e).message); }
    finally { setBusy(false); }
  }

  const n = state.projects.length;
  return (
    <aside className="side" id="side">
      <div className="brand"><div className="logo"><Play aria-hidden /></div><b>AutoEdit</b></div>
      <div className="snav">
        <div className={"sn" + (state.route.name === "schedule" ? "" : " on")} role="button" tabIndex={0}
          onClick={() => { if (state.route.name === "schedule") go({ name: "niche" }); }}><Clapperboard className="i" aria-hidden />Video</div>
        {state.hasSocialKey ? (
          <div className={"sn" + (state.route.name === "schedule" ? " on" : "")} role="button" tabIndex={0}
            onClick={() => go({ name: "schedule" })} onKeyDown={(e) => { if (e.key === "Enter") go({ name: "schedule" }); }}><CalendarDays className="i" aria-hidden />Lịch đăng</div>
        ) : (
          <div className="sn off" aria-disabled="true" role="button" tabIndex={0} title="Nhập key bundle.social ở Cài đặt → Kết nối"
            onClick={() => notify("Nhập key bundle.social ở Cài đặt → Kết nối")}><CalendarDays className="i" aria-hidden />Lịch đăng</div>
        )}
      </div>
      <button className="newbtn" onClick={() => go({ name: "niche" })}><Plus size={17} strokeWidth={2.4} aria-hidden />Video mới</button>
      <div className="plist">
        {state.projects.map((p) => (
          <div key={p.dir} className={"pi" + (cur === p.dir ? " on" : "")} role="button" tabIndex={0}
            onClick={() => { if (renaming !== p.dir) go({ name: "project", dir: p.dir }); }}
            onKeyDown={(e) => { if (e.key === "Enter" && renaming !== p.dir) go({ name: "project", dir: p.dir }); }}>
            <span className="av"><Film aria-hidden /></span>
            <div className="tx">
              {renaming === p.dir
                ? <NameInput value={p.title} onDone={(n) => void rename(p, n)} onCancel={() => setRenaming(null)} />
                : <b>{p.title}</b>}
              <span>{state.builds[p.dir] ? "đang dựng…" : `${nicheLabel(p.niche)} · ${p.created}`}</span>
            </div>
            <button className="more" aria-label={`Tuỳ chọn ${p.title}`} aria-expanded={menu === p.dir}
              onClick={(e) => { e.stopPropagation(); setMenu(menu === p.dir ? null : p.dir); }}><MoreHorizontal size={15} aria-hidden /></button>
            <i className={"st " + (state.builds[p.dir] ? BUILDING : DOT[p.status])}
              data-status={state.builds[p.dir] ? "building" : p.status} />
            {menu === p.dir && (
              <div className="pmenu" role="menu" onClick={(e) => e.stopPropagation()}>
                <button role="menuitem" onClick={() => { setMenu(null); setRenaming(p.dir); }}>Đổi tên</button>
                <button role="menuitem" className="danger" onClick={() => { setMenu(null); setDeleting(p); }}>Xoá…</button>
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="sidefoot">
        <div className="ministat"><span>{n} video</span></div>
        <div className="pi" role="button" tabIndex={0} onClick={() => go({ name: "settings" })}>
          <Settings className="i" aria-hidden /><div className="tx"><b>Cài đặt</b></div>
        </div>
      </div>
      {deleting && (
        <ConfirmDelete project={deleting} busy={busy} building={!!state.builds[deleting.dir]}
          onCancel={() => setDeleting(null)} onConfirm={() => void remove(deleting)} />
      )}
    </aside>
  );
}

function NameInput({ value, onDone, onCancel }: { value: string; onDone: (n: string) => void; onCancel: () => void }) {
  const [v, setV] = useState(value);
  const ref = useRef<HTMLInputElement>(null);
  const done = useRef(false);
  useEffect(() => { ref.current?.focus(); ref.current?.select(); }, []);
  const finish = (save: boolean) => {
    if (done.current) return;
    done.current = true;
    if (save) onDone(v); else onCancel();
  };
  return (
    <input ref={ref} aria-label="Tên video" value={v} maxLength={MAX_NAME}
      onClick={(e) => e.stopPropagation()} onChange={(e) => setV(e.target.value)} onBlur={() => finish(true)}
      onKeyDown={(e) => {
        e.stopPropagation();
        if (e.key === "Enter" && !e.nativeEvent.isComposing) finish(true);
        if (e.key === "Escape") finish(false);
      }} />
  );
}

function ConfirmDelete({ project: p, busy, building, onCancel, onConfirm }: {
  project: ProjectSummary; busy: boolean; building: boolean; onCancel: () => void; onConfirm: () => void;
}) {
  const scheduled = p.scheduledPosts ?? 0;
  return (
    <div className="modalbg" onClick={busy ? undefined : onCancel}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Xoá video" onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === "Escape" && !busy) onCancel(); }}>
        <h3>Xoá “{p.title}”?</h3>
        <div className="hint">Không hoàn tác được. Sẽ xoá:</div>
        <ul>
          <li>Bản chép clip, ảnh và dữ liệu AI (transcript, cache)</li>
          <li>Lịch sử trò chuyện với AI</li>
          <li>{p.runCount > 0 ? `${p.runCount} video đã xuất` : "Chưa có video đã xuất"}</li>
        </ul>
        <div className="hint" style={{ marginTop: 8 }}>File gốc của bạn (clip, ảnh, logo, nhạc ở thư mục ban đầu) được giữ nguyên.</div>
        {scheduled > 0 && (
          <div className="warn">{scheduled} bài đã hẹn giờ trên bundle.social vẫn sẽ được đăng. Huỷ ở mục Lịch đăng nếu không muốn đăng.</div>
        )}
        {building && <div className="warn">Video này đang được AI dựng: hãy dừng hoặc chờ xong rồi xoá.</div>}
        <div className="row">
          <button className="btn ghost" disabled={busy} onClick={onCancel} autoFocus>Huỷ</button>
          <button className="btn primary danger" disabled={busy || building} onClick={onConfirm}>{busy ? "Đang xoá…" : "Xoá"}</button>
        </div>
      </div>
    </div>
  );
}
