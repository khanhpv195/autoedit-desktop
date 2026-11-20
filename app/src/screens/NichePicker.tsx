import * as api from "../lib/api";
import { NICHES } from "../lib/niches";
import { useStore } from "../state/store";

export default function NichePicker() {
  const { state, dispatch, go } = useStore();
  async function choose(id: string) {
    if (state.settings) {
      const settings = { ...state.settings, lastNiche: id };
      dispatch({ type: "settings", settings });
      try { await api.saveSettings(settings); } catch { /* choosing a niche must not block */ }
    }
    go({ name: "new", niche: id });
  }
  return (
    <div className="view on">
      <h1>Hôm nay dựng video gì?</h1>
      <div className="sub">Chọn ngành hàng để AI dựng đúng kiểu.</div>
      <div className="catgrid">
        {NICHES.map((n) => (
          <div key={n.id} className="catcard" role="button" tabIndex={0} onClick={() => choose(n.id)}
            onKeyDown={(e) => { if (e.key === "Enter") choose(n.id); }}>
            {state.settings?.lastNiche === n.id && <span className="last">Lần trước</span>}
            <div className="big">{n.emoji}</div>
            <b>{n.label}</b>
            <small>{n.hint}</small>
          </div>
        ))}
      </div>
    </div>
  );
}
