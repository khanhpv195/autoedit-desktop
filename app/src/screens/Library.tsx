import { useEffect, useMemo, useState } from "react";
import { Film, Plus } from "lucide-react";
import { useStore } from "../state/store";
import * as api from "../lib/api";
import { backfillThumbs } from "../lib/engine";
import { nicheLabel } from "../lib/format";
import { filterProjects, NO_FILTER, type LibraryFilter, type SortKey, type StatusFilter } from "../lib/library";
import { DeleteDialog, NameInput, ProjectMenu, useProjectActions } from "../components/ProjectActions";

const DOT = { new: "new", done: "done", needs_review: "review" } as const;

let backfillStarted = false;
export function resetBackfillForTests() { backfillStarted = false; }

export default function Library() {
  const { state, go, refreshProjects } = useStore();
  const actions = useProjectActions();
  const [f, setF] = useState<LibraryFilter>(NO_FILTER);
  const all = state.projects;
  const shown = useMemo(() => filterProjects(all, state.builds, f), [all, state.builds, f]);
  const niches = useMemo(() => [...new Set(all.map((p) => p.niche))], [all]);

  useEffect(() => {
    const root = state.settings?.projectsRoot;
    if (backfillStarted || !root || !all.some((p) => p.runCount > 0 && !p.thumb)) return;
    backfillStarted = true;
    backfillThumbs(root, () => { refreshProjects().catch(() => {}); }).then(() => refreshProjects()).catch(() => {});
  }, [all, state.settings, refreshProjects]);

  if (all.length === 0) {
    return (
      <div className="lib">
        <h2>Thư viện video</h2>
        <div className="lib-empty">
          <b>Chưa có video nào</b>
          <button className="btn primary" onClick={() => go({ name: "niche" })}><Plus size={16} aria-hidden />Video mới</button>
        </div>
      </div>
    );
  }

  return (
    <div className="lib">
      <h2>Thư viện video <span className="muted">· {all.length} video</span></h2>
      <div className="lib-bar">
        <input type="search" placeholder="Tìm theo tên…" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} />
        <select aria-label="Ngách" value={f.niche} onChange={(e) => setF({ ...f, niche: e.target.value })}>
          <option value="">Tất cả ngách</option>
          {niches.map((n) => <option key={n} value={n}>{nicheLabel(n)}</option>)}
        </select>
        <select aria-label="Trạng thái" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as StatusFilter })}>
          <option value="all">Tất cả trạng thái</option>
          <option value="done">Xong</option>
          <option value="needs_review">Cần xem lại</option>
          <option value="building">Đang dựng</option>
          <option value="new">Mới</option>
        </select>
        <select aria-label="Sắp xếp" value={f.sort} onChange={(e) => setF({ ...f, sort: e.target.value as SortKey })}>
          <option value="new">Mới nhất</option>
          <option value="old">Cũ nhất</option>
          <option value="name">Tên A–Z</option>
        </select>
      </div>
      {shown.length === 0 ? (
        <div className="lib-empty">
          <b>Không có video khớp bộ lọc</b>
          <button className="btn ghost" onClick={() => setF(NO_FILTER)}>Xoá bộ lọc</button>
        </div>
      ) : (
        <div className="lib-grid">
          {shown.map((p) => {
            const building = !!state.builds[p.dir];
            return (
              <div key={p.dir} className="lib-card" role="button" tabIndex={0}
                onClick={() => { if (actions.renaming !== p.dir) go({ name: "project", dir: p.dir }); }}
                onKeyDown={(e) => { if (e.target !== e.currentTarget) return; if (e.key === "Enter" && actions.renaming !== p.dir) go({ name: "project", dir: p.dir }); }}>
                <div className="lib-thumb">
                  {building ? <span className="lib-ph">đang dựng…</span>
                    : p.thumb ? <img src={api.fileSrc(p.thumb)} alt={p.title} loading="lazy" />
                    : <Film className="lib-ph" aria-hidden />}
                  <i className={"st " + (building ? "run" : DOT[p.status])} />
                </div>
                <div className="lib-meta">
                  {actions.renaming === p.dir
                    ? <NameInput value={p.title} onDone={(n) => void actions.rename(p, n)} onCancel={() => actions.setRenaming(null)} />
                    : <b>{p.title}</b>}
                  <span>{nicheLabel(p.niche)} · {p.created} · {p.runCount} lần xuất</span>
                  <ProjectMenu p={p} actions={actions} />
                </div>
              </div>
            );
          })}
        </div>
      )}
      <DeleteDialog actions={actions} />
    </div>
  );
}
