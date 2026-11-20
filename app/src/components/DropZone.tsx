import { useEffect, useRef, useState } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import * as api from "../lib/api";
import { useStore } from "../state/store";

type Props = {
  kind: "clip" | "logo" | "music";
  label: string;
  hint?: string;
  accept: string[];
  onFile: (path: string) => void;
  variant?: "big" | "slot";
  dragDrop?: boolean;
  value?: string | null;
  disabled?: boolean;
};

const ext = (p: string) => p.split(".").pop()?.toLowerCase() ?? "";
const baseName = (p: string) => p.split(/[\\/]/).pop() ?? p;

export default function DropZone({ kind, label, hint, accept, onFile, variant = "big", dragDrop = false, value, disabled }: Props) {
  const { notify } = useStore();
  const ref = useRef<HTMLDivElement>(null);
  const [over, setOver] = useState(false);
  const propsRef = useRef({ accept, onFile, notify, disabled });
  propsRef.current = { accept, onFile, notify, disabled };

  function take(path: string) {
    if (!propsRef.current.accept.includes(ext(path))) { propsRef.current.notify("File không đúng loại"); return; }
    propsRef.current.onFile(path);
  }

  async function pick() {
    if (disabled) return;
    const p = await api.pickFile(kind);
    if (p) take(p);
  }

  useEffect(() => {
    if (!dragDrop) return;
    let un: (() => void) | undefined;
    let dead = false;
    const inside = (pos: { x: number; y: number }) => {
      const r = ref.current?.getBoundingClientRect();
      if (!r) return false;
      const x = pos.x / window.devicePixelRatio, y = pos.y / window.devicePixelRatio;
      return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
    };
    try {
      getCurrentWebview().onDragDropEvent((e) => {
        const p = e.payload;
        if (p.type === "leave") setOver(false);
        else if (p.type === "over") setOver(inside(p.position));
        else if (p.type === "drop") {
          setOver(false);
          if (!propsRef.current.disabled && inside(p.position) && p.paths[0]) take(p.paths[0]);
        }
      }).then((f) => { if (dead) f(); else un = f; }).catch(() => {});
    } catch { /* not running inside Tauri (tests, browser) */ }
    return () => { dead = true; un?.(); };
  }, [dragDrop]);

  if (variant === "slot") {
    return (
      <div ref={ref} className={"slot" + (value ? " set" : "")} role="button" tabIndex={0} onClick={pick}
        onKeyDown={(e) => { if (e.key === "Enter") pick(); }}>
        <span className="ic">{kind === "logo" ? "🏷️" : "🎵"}</span>
        <div><b>{label}</b><small>{value ? baseName(value) : hint}</small></div>
      </div>
    );
  }
  return (
    <div ref={ref} className={"drop" + (over ? " over" : "")} role="button" tabIndex={0} onClick={pick}
      onKeyDown={(e) => { if (e.key === "Enter") pick(); }}>
      <div className="ic">🎬</div>
      <b>{label}</b>
      <small>{hint}</small>
    </div>
  );
}
