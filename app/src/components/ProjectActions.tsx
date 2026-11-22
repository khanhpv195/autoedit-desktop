import { useEffect, useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { useStore } from "../state/store";
import * as api from "../lib/api";
import { toEngineError } from "../lib/errors";
import { MAX_NAME } from "../lib/defaults";
import type { ProjectSummary } from "../lib/types";

export function useProjectActions() {
  const { state, go, notify, refreshProjects } = useStore();
  const [menu, setMenu] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const openDir = state.route.name === "project" || state.route.name === "new" ? state.route.dir ?? null : null;

  // A click anywhere else closes the ⋯ menu.
  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [menu]);

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

  return { menu, setMenu, renaming, setRenaming, deleting, setDeleting, busy, rename, remove };
}

export function ProjectMenu({ p, actions }: { p: ProjectSummary; actions: ReturnType<typeof useProjectActions> }) {
  const { menu, setMenu, setRenaming, setDeleting } = actions;
  return (
    <>
      <button className="more" aria-label={`Tuỳ chọn ${p.title}`} aria-expanded={menu === p.dir}
        onClick={(e) => { e.stopPropagation(); setMenu(menu === p.dir ? null : p.dir); }}><MoreHorizontal size={15} aria-hidden /></button>
      {menu === p.dir && (
        <div className="pmenu" role="menu" onClick={(e) => e.stopPropagation()}>
          <button role="menuitem" onClick={() => { setMenu(null); setRenaming(p.dir); }}>Đổi tên</button>
          <button role="menuitem" className="danger" onClick={() => { setMenu(null); setDeleting(p); }}>Xoá…</button>
        </div>
      )}
    </>
  );
}

export function DeleteDialog({ actions }: { actions: ReturnType<typeof useProjectActions> }) {
  const { state } = useStore();
  const { deleting, setDeleting, busy, remove } = actions;
  if (!deleting) return null;
  return (
    <ConfirmDelete project={deleting} busy={busy} building={!!state.builds[deleting.dir]}
      onCancel={() => setDeleting(null)} onConfirm={() => void remove(deleting)} />
  );
}

export function NameInput({ value, onDone, onCancel }: { value: string; onDone: (n: string) => void; onCancel: () => void }) {
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

export function ConfirmDelete({ project: p, busy, building, onCancel, onConfirm }: {
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
