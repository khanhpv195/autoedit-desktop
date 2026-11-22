import { useState } from "react";
import * as api from "../lib/api";
import { MAX_NAME } from "../lib/defaults";
import { toEngineError } from "../lib/errors";
import { useStore } from "../state/store";

/** A project title the customer clicks to rename (Enter / blur saves, Esc cancels). */
export default function EditableTitle({ dir, title, as: Tag = "h1", onRenamed }: {
  dir: string; title: string; as?: "h1" | "h2"; onRenamed?: () => void;
}) {
  const { refreshProjects, notify } = useStore();
  const [editing, setEditing] = useState<string | null>(null);

  async function save() {
    const v = editing;
    setEditing(null);
    if (v === null || v.trim() === title) return;
    try { await api.renameProject(dir, v); await refreshProjects(); onRenamed?.(); }
    catch (e) { notify(toEngineError(e).message); }
  }

  if (editing !== null) {
    return (
      <Tag>
        <input autoFocus aria-label="Tên video" value={editing} maxLength={MAX_NAME}
          onChange={(e) => setEditing(e.target.value)} onBlur={() => void save()}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.nativeEvent.isComposing) void save();
            if (e.key === "Escape") setEditing(null);
          }} />
      </Tag>
    );
  }
  return (
    <Tag>
      <button className="titleedit" title="Bấm để đổi tên" onClick={() => setEditing(title)}>{title}</button>
    </Tag>
  );
}
