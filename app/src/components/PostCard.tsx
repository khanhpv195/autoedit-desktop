import { useEffect, useMemo, useRef, useState } from "react";
import * as engine from "../lib/engine";
import { toEngineError, type AnyEngineError } from "../lib/errors";
import { V2_CHANNELS, channelLabel, localIso, postTime, toInputValue } from "../lib/format";
import type { Post, ProjectDetail, Run } from "../lib/types";
import { useStore } from "../state/store";
import ErrorPanel from "./ErrorPanel";

type When = "now" | "pick" | "queue";

function defaultPick(): string {
  const d = new Date();
  d.setHours(19, 30, 0, 0);
  if (d.getTime() <= Date.now()) d.setDate(d.getDate() + 1);
  return toInputValue(d);
}

export default function PostCard({ detail, run, onPosted }: { detail: ProjectDetail; run: Run; onPosted?: () => void }) {
  const { state, dispatch, go } = useStore();
  const hasKey = state.hasSocialKey;
  const team = state.social?.teams.find((t) => t.id === state.settings?.socialTeamId) ?? state.social?.teams[0] ?? null;
  const available = useMemo(
    () => [...new Set((team?.channels ?? []).map((c) => c.type))].filter((t) => V2_CHANNELS.includes(t)),
    [team],
  );

  const existing = (detail.posts ?? []).filter((p) => p.run === run.n);
  const [showForm, setShowForm] = useState(existing.length === 0);
  const [selected, setSelected] = useState<string[] | null>(null);
  const [caption, setCaption] = useState("");
  const [captionBusy, setCaptionBusy] = useState(false);
  const [when, setWhen] = useState<When>("now");
  const [pick, setPick] = useState(defaultPick);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState("");
  const [error, setError] = useState<AnyEngineError | null>(null);
  const [done, setDone] = useState<Post | null>(null);
  const captionFor = useRef<string | null>(null);

  // The team's channels come from one account read, cached in the store.
  useEffect(() => {
    if (!hasKey || state.social) return;
    engine.socialCheck().then((acc) => dispatch({ type: "social", social: acc })).catch((e) => setError(toEngineError(e)));
  }, [hasKey, state.social, dispatch]);

  useEffect(() => { if (selected === null && team) setSelected(available); }, [team, available, selected]);

  async function writeCaption() {
    setCaptionBusy(true);
    try { setCaption(await engine.socialCaption(detail.dir, run.n)); }
    catch (e) { setError(toEngineError(e)); }
    finally { setCaptionBusy(false); }
  }

  // First time the form opens for this run: let the AI write the caption.
  const ready = hasKey && !!team && showForm;
  useEffect(() => {
    const id = `${detail.dir}#${run.n}`;
    if (!ready || captionFor.current === id) return;
    captionFor.current = id;
    void writeCaption();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, detail.dir, run.n]);

  if (!hasKey) {
    return (
      <div className="card">
        <h3>Đăng bài</h3>
        <div className="hint" style={{ marginBottom: 10 }}>Bật đăng bài tự động: Cài đặt → Kết nối</div>
        <button className="btn ghost" onClick={() => go({ name: "settings", tab: "conn" })}>Mở Cài đặt</button>
      </div>
    );
  }

  const chosen = selected ?? [];
  const toggleCh = (t: string) => setSelected(chosen.includes(t) ? chosen.filter((x) => x !== t) : [...chosen, t]);
  const canPost = !!team && chosen.length > 0 && caption.trim().length > 0 && !busy && (when !== "pick" || !!pick);

  async function publish() {
    if (!team) return;
    setBusy(true);
    setError(null);
    setStep("Đang chuẩn bị…");
    try {
      const w = when === "pick" ? localIso(new Date(pick)) : when;
      const post = await engine.socialPublish(
        { dir: detail.dir, run: run.n, team: team.id, channels: chosen, caption: caption.trim(), when: w },
        (label, p) => setStep(label || `Đang đăng… ${Math.round(p * 100)}%`),
      );
      setDone(post);
      onPosted?.();
    } catch (e) { setError(toEngineError(e)); }
    finally { setBusy(false); setStep(""); }
  }

  const summary = (p: { postDate: string; channels: string[] }) =>
    `${postTime(p.postDate)} · ${p.channels.map(channelLabel).join(", ")}`;

  if (done) {
    return (
      <div className="card">
        <h3>Đăng bài</h3>
        <div className="okline">Đã lên lịch {summary(done)}</div>
        <div style={{ marginTop: 10 }}>
          <button className="btn ghost" onClick={() => { setDone(null); setShowForm(true); }}>Đăng thêm</button>
        </div>
      </div>
    );
  }

  if (!showForm) {
    return (
      <div className="card">
        <h3>Đăng bài</h3>
        {existing.map((p) => <div key={p.id} className="okline">Đã lên lịch {summary(p)} <span className="hint">({p.status})</span></div>)}
        <div style={{ marginTop: 10 }}><button className="btn ghost" onClick={() => setShowForm(true)}>Đăng thêm</button></div>
      </div>
    );
  }

  return (
    <div className="card">
      <h3>Đăng bài</h3>
      {!team ? (
        <div className="hint">{error ? "" : "Đang đọc kênh…"}</div>
      ) : (
        <div className="stack">
          <div>
            <div className="label">Đăng lên</div>
            <div className="chans">
              {available.length === 0 && <span className="hint">Team chưa nối kênh nào hỗ trợ đăng video.</span>}
              {available.map((t) => (
                <label key={t} className={"ch" + (chosen.includes(t) ? " on" : "")}>
                  <input type="checkbox" style={{ display: "none" }} checked={chosen.includes(t)} onChange={() => toggleCh(t)} />
                  {channelLabel(t)}
                </label>
              ))}
            </div>
          </div>
          <div>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div className="label">Caption</div>
              <button className="btn ghost" style={{ padding: "4px 10px" }} disabled={captionBusy} onClick={() => void writeCaption()}>↻ Viết lại</button>
            </div>
            <textarea aria-label="Caption" value={caption} maxLength={2200} onChange={(e) => setCaption(e.target.value)}
              placeholder={captionBusy ? "AI đang viết caption…" : "Caption"} />
          </div>
          <div className="stack" style={{ gap: 8 }}>
            <label className="row"><input type="radio" name="when" checked={when === "now"} onChange={() => setWhen("now")} /> Đăng ngay</label>
            <label className="row"><input type="radio" name="when" checked={when === "pick"} onChange={() => setWhen("pick")} /> Chọn giờ
              <input type="datetime-local" aria-label="Giờ đăng" value={pick} disabled={when !== "pick"} onChange={(e) => setPick(e.target.value)} />
            </label>
            <label className="row"><input type="radio" name="when" checked={when === "queue"} onChange={() => setWhen("queue")} /> Vào hàng đợi
              <span className="hint">slot routine kế tiếp, hoặc 19:30 ngày mai</span></label>
          </div>
          {error && <ErrorPanel error={error} compact onSettings={() => go({ name: "settings", tab: "conn" })} />}
          <div className="buildrow">
            <button className="btn primary" disabled={!canPost} onClick={() => void publish()}>{busy ? step || "Đang đăng…" : "Đăng"}</button>
          </div>
        </div>
      )}
    </div>
  );
}
