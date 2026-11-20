import { useEffect, useState } from "react";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import * as api from "../lib/api";

export default function UpdateBanner() {
  const [update, setUpdate] = useState<Update | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    check()
      .then((u) => { if (alive && u) setUpdate(u); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  if (!update) return null;

  const install = async () => {
    setBusy(true);
    try {
      await update.downloadAndInstall();
      try { await api.killAllJobs(); } catch { /* ignore */ } // relaunch must not leave an engine running headless
      await relaunch();
    } catch {
      setBusy(false);
    }
  };

  return (
    <div className="update-banner" role="status">
      <span>Có bản mới {update.version}</span>
      <button className="btn" onClick={install} disabled={busy}>{busy ? "Đang cập nhật…" : "Cập nhật"}</button>
    </div>
  );
}
