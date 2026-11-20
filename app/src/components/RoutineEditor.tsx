import { CHANNELS, V2_CHANNELS, channelLabel } from "../lib/format";
import type { Routine } from "../lib/types";

type Props = {
  routines: Routine[];
  /** Channel types the team can post to (subset of the four v2 channels). */
  channels: string[];
  running: boolean;
  onChange(next: Routine[]): void;
  onRunNow(): void;
};

export default function RoutineEditor({ routines, channels, running, onChange, onRunNow }: Props) {
  const options = channels.length ? channels : V2_CHANNELS;
  const patch = (id: string, p: Partial<Routine>) => onChange(routines.map((r) => (r.id === id ? { ...r, ...p } : r)));
  const add = () => onChange([...routines, { id: `r${Date.now().toString(36)}${routines.length}`, time: "19:30", channels: [...options], enabled: true }]);

  return (
    <div className="card" style={{ marginTop: 18 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>Routine tự động</h3>
        <span className="row">
          <button className="btn ghost" disabled={running} onClick={onRunNow}>{running ? "Đang chạy…" : "Chạy ngay"}</button>
          <button className="btn dark" onClick={add}>＋ Thêm routine</button>
        </span>
      </div>
      <div className="hint" style={{ margin: "6px 0" }}>Mỗi ngày đăng video mới nhất chưa đăng. Routine chỉ chạy khi app mở. Bài đã lên lịch vẫn đăng khi máy tắt.</div>
      {routines.length === 0 && <div className="hint">Chưa có routine nào.</div>}
      {routines.map((r, i) => (
        <div key={r.id} className="rt">
          <div className="tx">
            <b className="row" style={{ display: "flex" }}>
              Mỗi ngày lúc{" "}
              <input type="time" aria-label={`Giờ routine ${i + 1}`} value={r.time} onChange={(e) => e.target.value && patch(r.id, { time: e.target.value })} />
            </b>
            <span className="chans" style={{ margin: "6px 0 0" }}>
              {options.map((c) => (
                <label key={c} className={"ch" + (r.channels.includes(c) ? " on" : "")}>
                  <input type="checkbox" style={{ display: "none" }} aria-label={`${channelLabel(c)} routine ${i + 1}`}
                    checked={r.channels.includes(c)}
                    onChange={() => patch(r.id, { channels: r.channels.includes(c) ? r.channels.filter((x) => x !== c) : [...r.channels, c] })} />
                  {CHANNELS[c] ?? c}
                </label>
              ))}
            </span>
          </div>
          <span className={"sw" + (r.enabled ? " on" : "")} role="switch" aria-checked={r.enabled} aria-label={`Bật routine ${i + 1}`} tabIndex={0}
            onClick={() => patch(r.id, { enabled: !r.enabled })} onKeyDown={(e) => { if (e.key === "Enter") patch(r.id, { enabled: !r.enabled }); }} />
          <button className="btn ghost" aria-label={`Xóa routine ${i + 1}`} onClick={() => onChange(routines.filter((x) => x.id !== r.id))}>✕</button>
        </div>
      ))}
    </div>
  );
}
