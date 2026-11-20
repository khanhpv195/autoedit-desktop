import { useEffect, useState } from "react";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";

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
