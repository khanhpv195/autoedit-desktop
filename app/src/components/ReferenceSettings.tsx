import { useEffect, useState } from "react";
import * as engine from "../lib/engine";
import { toEngineError } from "../lib/errors";
import type { Reference } from "../lib/types";

const NICHES: Record<string, string> = {
  "thoi-trang": "Thời trang", "my-pham": "Mỹ phẩm", "do-an": "Đồ ăn", "phu-kien": "Phụ kiện", chung: "Khác",
};

/** Settings card: the video mẫu the customer saved ("Lưu làm mẫu" on a result), each can be removed. */
export default function ReferenceSettings() {
  const [refs, setRefs] = useState<Reference[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await engine.listReferences();
        if (alive) setRefs(r ?? []);
      } catch (e) {
        if (alive) { setRefs([]); setErr(toEngineError(e).message || "Không đọc được video mẫu"); }
      }
    })();
    return () => { alive = false; };
  }, []);

  async function remove(id: string) {
    setBusy(id); setErr("");
    try { setRefs(await engine.deleteReference(id)); }
    catch (e) { setErr(toEngineError(e).message || "Không bỏ được video mẫu"); }
    finally { setBusy(null); }
  }

  return (
    <div className="card">
      <h3>Video mẫu</h3>
      <div className="hint" style={{ marginBottom: 8 }}>
        AI dựng theo cách của các video mẫu (mẫu Clip-chuan có sẵn, cộng 2 mẫu mới nhất anh/chị lưu, ưu tiên cùng ngành).
        Lưu mẫu bằng nút "Lưu làm mẫu" ở màn kết quả.
      </div>
      {refs === null ? <div className="hint"><span className="spin" /> Đang tải…</div>
        : refs.length === 0 ? <div className="hint">Chưa lưu video mẫu nào.</div>
        : (
          <ul className="reflist" aria-label="Video mẫu đã lưu">
            {refs.map((r) => (
              <li key={r.id} className="row" style={{ justifyContent: "space-between" }}>
                <span>{r.name} · lần {r.run} · {NICHES[r.niche] ?? r.niche}</span>
                <button className="btn ghost" disabled={busy !== null} onClick={() => void remove(r.id)}
                  aria-label={`Bỏ mẫu ${r.name}`}>{busy === r.id ? <span className="spin" /> : "Bỏ mẫu"}</button>
              </li>
            ))}
          </ul>
        )}
      {err && <div className="err" role="alert" style={{ marginTop: 8, padding: 10, fontSize: 13 }}>{err}</div>}
    </div>
  );
}
