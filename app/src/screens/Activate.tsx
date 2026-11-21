import { useState } from "react";
import * as api from "../lib/api";
import { licenseMessage } from "../lib/license";

export default function Activate({ reason, onDone }: { reason?: string; onDone: () => void }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(reason ? licenseMessage(reason) : null);

  async function submit() {
    setBusy(true); setErr(null);
    try {
      await api.licenseActivate(key.trim());
      onDone();
    } catch (e) {
      setErr(licenseMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="activate">
      <div className="activate-card card">
        <h1>Kích hoạt AutoEdit</h1>
        <p className="sub">Dán key bạn nhận được từ người bán rồi bấm Kích hoạt. Mỗi key dùng cho một máy.</p>
        <input value={key} onChange={(e) => setKey(e.target.value)} placeholder="AE-XXXX-XXXX-XXXX-XXXX"
          autoFocus spellCheck={false} onKeyDown={(e) => { if (e.key === "Enter" && key.trim() && !busy) void submit(); }} />
        {err && <div className="activate-err" role="alert">{err}</div>}
        <button className="btn primary big" disabled={!key.trim() || busy} onClick={submit}>
          {busy ? "Đang kích hoạt…" : "Kích hoạt"}
        </button>
      </div>
    </div>
  );
}
