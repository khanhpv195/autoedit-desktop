import { useEffect, useMemo, useState } from "react";
import * as engine from "../lib/engine";
import { toEngineError, type AnyEngineError } from "../lib/errors";
import { STATUS_VI, V2_CHANNELS, channelLabel, localIso, postTime, toInputValue } from "../lib/format";
import type { Post, ProjectDetail, Run } from "../lib/types";
import { publishKey, useStore } from "../state/store";
import ErrorPanel from "./ErrorPanel";

type When = "now" | "pick" | "queue";

function defaultPick(): string {
  const d = new Date();
  d.setHours(19, 30, 0, 0);
  if (d.getTime() <= Date.now()) d.setDate(d.getDate() + 1);
  return toInputValue(d);
}

const DAY = 24 * 3600 * 1000;

export default function PostCard({ detail, run, onPosted }: { detail: ProjectDetail; run: Run; onPosted?: () => void }) {
  const { state, dispatch, go, startPublish, cancelPublish } = useStore();
  const hasKey = state.hasSocialKey;
  const account = state.social;
  const team = account?.teams.find((t) => t.id === state.settings?.socialTeamId) ?? account?.teams[0] ?? null;
  const available = useMemo(
    () => [...new Set((team?.channels ?? []).map((c) => c.type))].filter((t) => V2_CHANNELS.includes(t)),
    [team],
  );
  const key = publishKey(detail.dir, run.n);
  const inflight = state.publishes[key];
  const done: Post | undefined = state.publishDone[key];
  const publishError = state.publishErrors[key] ?? null;

  const existing = (detail.posts ?? []).filter((p) => p.run === run.n);
  const [showForm, setShowForm] = useState(existing.length === 0);
  const [selected, setSelected] = useState<string[] | null>(null);
  const [caption, setCaption] = useState("");
  const [captionBusy, setCaptionBusy] = useState(false);
  const [captionError, setCaptionError] = useState<AnyEngineError | null>(null);
  const [when, setWhen] = useState<When>("now");
  const [pick, setPick] = useState(defaultPick);
  const [accountError, setAccountError] = useState<AnyEngineError | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [live, setLive] = useState<Record<string, Post>>({});
  const toConn = () => go({ name: "settings", tab: "conn" });

  // The team's channels come from one account read, cached in the store.
  useEffect(() => {
    if (!hasKey || state.social) return;
    let alive = true;
    setAccountError(null);
    engine.socialCheck()
      .then((acc) => { if (alive) dispatch({ type: "social", social: acc }); })
      .catch((e) => { if (alive) setAccountError(toEngineError(e)); });
    return () => { alive = false; };
  }, [hasKey, state.social, dispatch, attempt]);

  useEffect(() => { if (selected === null && team) setSelected(available); }, [team, available, selected]);

  // Posts already made for this run: ask bundle.social for their live status around their dates.
  const postsSig = existing.map((p) => `${p.id}@${p.postDate}`).join("|");
  useEffect(() => {
    if (!team || existing.length === 0) return;
    let alive = true;
    const times = existing.map((p) => new Date(p.postDate).getTime()).filter((t) => !Number.isNaN(t));
    if (times.length === 0) return;
    const from = localIso(new Date(Math.min(...times) - DAY));
    const to = localIso(new Date(Math.max(...times) + DAY));
    void (async () => {
      try {
        const posts = await engine.socialList(team.id, from, to);
        if (alive && posts) setLive(Object.fromEntries(posts.map((p) => [p.id, p])));
      } catch { /* keep the status saved in project.json */ }
    })();
    return () => { alive = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [team?.id, postsSig]);

  async function writeCaption() {
    setCaptionBusy(true);
    setCaptionError(null);
    try { setCaption(await engine.socialCaption(detail.dir, run.n)); }
    catch (e) { setCaptionError(toEngineError(e)); }
    finally { setCaptionBusy(false); }
  }

  // onPosted reloads the project so the saved post list catches up.
  useEffect(() => { if (done) onPosted?.(); }, [done]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!hasKey) {
    return (
      <div className="card">
        <h3>Đăng bài</h3>
        <div className="hint" style={{ marginBottom: 10 }}>Bật đăng bài tự động: Cài đặt → Kết nối</div>
        <button className="btn ghost" onClick={toConn}>Mở Cài đặt</button>
      </div>
    );
  }

  // Publishing survives leaving this screen: show its progress instead of a fresh form.
  if (inflight) {
    return (
      <div className="card">
        <h3>Đăng bài</h3>
        <div className="hint" style={{ marginBottom: 10 }}>
          {inflight.label || `Đang đăng… ${Math.round(inflight.progress * 100)}%`}
        </div>
        <button className="btn ghost" onClick={() => cancelPublish(key)}>Hủy</button>
      </div>
    );
  }

  const chosen = selected ?? [];
  const toggleCh = (t: string) => setSelected(chosen.includes(t) ? chosen.filter((x) => x !== t) : [...chosen, t]);
  const canPost = !!team && chosen.length > 0 && caption.trim().length > 0 && (when !== "pick" || !!pick);

  function publish() {
    if (!team) return;
    const w = when === "pick" ? localIso(new Date(pick)) : when;
    startPublish({ dir: detail.dir, run: run.n, team: team.id, channels: chosen, caption: caption.trim(), when: w });
  }

  const summary = (p: { postDate: string; channels: string[] }) =>
    `${postTime(p.postDate)} · ${p.channels.map(channelLabel).join(", ")}`;

  if (done) {
    return (
      <div className="card">
        <h3>Đăng bài</h3>
        <div className="okline">Đã lên lịch {summary(done)}</div>
        <div style={{ marginTop: 10 }}>
          <button className="btn ghost" onClick={() => { dispatch({ type: "publishClear", key }); setShowForm(true); }}>Đăng thêm</button>
        </div>
      </div>
    );
  }

  if (!showForm) {
    return (
      <div className="card">
        <h3>Đăng bài</h3>
        {existing.map((p) => {
          const l = live[p.id];
          const status = l?.status ?? p.status;
          return (
            <div key={p.id} className={status === "ERROR" ? "errline" : "okline"}>
              {STATUS_VI[status] ?? status} {summary(l ?? p)}
              {l?.error && <span className="hint"> {l.error}</span>}
            </div>
          );
        })}
        <div style={{ marginTop: 10 }}><button className="btn ghost" onClick={() => setShowForm(true)}>Đăng thêm</button></div>
      </div>
    );
  }

  if (!team) {
    return (
      <div className="card">
        <h3>Đăng bài</h3>
        {accountError ? (
          <div className="stack">
            <ErrorPanel error={accountError} context="social" compact />
            <div className="row">
              <button className="btn ghost" onClick={() => setAttempt((n) => n + 1)}>Thử lại</button>
              <button className="btn ghost" onClick={toConn}>Mở Cài đặt → Kết nối &amp; MCP</button>
            </div>
          </div>
        ) : account ? (
          <div className="stack">
            <div className="errline">Chưa có team/kênh trên bundle.social</div>
            <div className="hint">Tạo team và nối kênh trên bundle.social (portal quản lý kênh), rồi bấm Làm mới.</div>
            <div className="row">
              <button className="btn ghost" onClick={() => dispatch({ type: "social", social: null })}>Làm mới</button>
              <button className="btn ghost" onClick={toConn}>Mở Cài đặt → Kết nối &amp; MCP</button>
            </div>
          </div>
        ) : (
          <div className="hint">Đang đọc kênh…</div>
        )}
      </div>
    );
  }

  return (
    <div className="card">
      <h3>Đăng bài</h3>
      <div className="stack">
        <div>
          <div className="label">Đăng lên</div>
          <div className="chans">
            {available.length === 0 && (
              <span className="hint">
                Chưa có kênh nào hỗ trợ đăng video (TikTok, Instagram, YouTube, Facebook) trong team này.{" "}
                <button className="btn ghost" style={{ padding: "2px 8px" }} onClick={toConn}>Mở Cài đặt → Kết nối &amp; MCP</button>
              </span>
            )}
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
            <button className="btn ghost" style={{ padding: "4px 10px" }} disabled={captionBusy} onClick={() => void writeCaption()}>
              {captionBusy ? "AI đang viết…" : caption.trim() ? "↻ Viết lại" : "✨ Viết caption bằng AI"}
            </button>
          </div>
          <textarea aria-label="Caption" value={caption} maxLength={2200} onChange={(e) => setCaption(e.target.value)}
            placeholder={captionBusy ? "AI đang viết caption…" : "Nhập caption hoặc bấm ✨ để AI viết"} />
          {captionError && <ErrorPanel error={captionError} context="caption" compact onSettings={toConn} />}
        </div>
        <div className="stack" style={{ gap: 8 }}>
          <label className="row"><input type="radio" name="when" checked={when === "now"} onChange={() => setWhen("now")} /> Đăng ngay</label>
          <label className="row"><input type="radio" name="when" checked={when === "pick"} onChange={() => setWhen("pick")} /> Chọn giờ
            <input type="datetime-local" aria-label="Giờ đăng" value={pick} disabled={when !== "pick"} onChange={(e) => setPick(e.target.value)} />
          </label>
          <label className="row"><input type="radio" name="when" checked={when === "queue"} onChange={() => setWhen("queue")} /> Vào hàng đợi
            <span className="hint">slot routine kế tiếp, hoặc 19:30 ngày mai</span></label>
        </div>
        {publishError && <ErrorPanel error={publishError} context="social" compact onSettings={toConn} />}
        <div className="buildrow">
          <button className="btn primary" disabled={!canPost} onClick={publish}>Đăng</button>
        </div>
      </div>
    </div>
  );
}
