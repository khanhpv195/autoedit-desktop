import { useCallback, useEffect, useMemo, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import RoutineEditor from "../components/RoutineEditor";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { describeError, toEngineError, type AnyEngineError } from "../lib/errors";
import { V2_CHANNELS, channelLabel, hhmm, localIso, postTime, weekRange } from "../lib/format";
import type { Post, Routine } from "../lib/types";
import { useStore } from "../state/store";

const DAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const COLOR: Record<string, string> = { SCHEDULED: "#2563eb", POSTED: "#16a34a", ERROR: "#dc2626" };
const colorOf = (s: string) => COLOR[s] ?? "#9ca3af";
const STATUS_VI: Record<string, string> = { SCHEDULED: "Đã lên lịch", POSTED: "Đã đăng", ERROR: "Lỗi", PROCESSING: "Đang xử lý" };
const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

export default function Schedule() {
  const { state, dispatch, go, notify } = useStore();
  const settings = state.settings;
  const team = settings?.socialTeamId ?? state.social?.teams[0]?.id ?? null;
  const [offset, setOffset] = useState(0);
  const [mode, setMode] = useState<"week" | "list">("week");
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<AnyEngineError | null>(null);
  const [sel, setSel] = useState<Post | null>(null);
  const [running, setRunning] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const range = useMemo(() => weekRange(new Date(), offset), [offset]);
  const from = localIso(range.from);
  const to = localIso(range.to);

  const load = useCallback(async () => {
    if (!team) return;
    setLoading(true);
    setError(null);
    try { setPosts(await engine.socialList(team, from, to)); }
    catch (e) { setError(toEngineError(e)); }
    finally { setLoading(false); }
  }, [team, from, to]);
  useEffect(() => { void load(); }, [load]);

  // Channels of the team (for new routines) come from the cached account read.
  useEffect(() => {
    if (state.hasSocialKey && !state.social) {
      engine.socialCheck().then((acc) => dispatch({ type: "social", social: acc })).catch(() => {});
    }
  }, [state.hasSocialKey, state.social, dispatch]);

  if (!state.hasSocialKey || !team) {
    return (
      <div className="view on">
        <div className="lock">
          <div className="big">📅</div>
          <h2>Chưa bật đăng bài tự động</h2>
          <p>Dán API key bundle.social để đăng và lên lịch video.</p>
          <button className="btn primary" onClick={() => go({ name: "settings", tab: "conn" })}>Nhập key bundle.social</button>
        </div>
      </div>
    );
  }

  const channels = (state.social?.teams.find((t) => t.id === team)?.channels ?? [])
    .map((c) => c.type).filter((t, i, a) => V2_CHANNELS.includes(t) && a.indexOf(t) === i);

  const days = DAYS.map((label, i) => {
    const d = new Date(range.from.getFullYear(), range.from.getMonth(), range.from.getDate() + i);
    const ps = posts.filter((p) => dayKey(new Date(p.postDate)) === dayKey(d))
      .sort((a, b) => new Date(a.postDate).getTime() - new Date(b.postDate).getTime());
    return { label, d, ps, today: dayKey(d) === dayKey(new Date()) };
  });
  const title = `${range.from.getDate()}/${range.from.getMonth() + 1} – ${new Date(range.to.getTime() - 1).getDate()}/${new Date(range.to.getTime() - 1).getMonth() + 1}`;

  async function saveRoutines(routines: Routine[]) {
    if (!settings) return;
    const next = { ...settings, routines };
    dispatch({ type: "settings", settings: next });
    try { await api.saveSettings(next); } catch (e) { notify(toEngineError(e).message); }
  }

  async function runNow() {
    if (!team) return;
    setRunning(true);
    try {
      const r = await engine.routineSync(team);
      notify(r.skipped ?? `Đã tạo ${r.created.length} bài cho 7 ngày tới`);
      await load();
    } catch (e) { const d = describeError(toEngineError(e)); notify(`${d.title}. ${d.detail}`); }
    finally { setRunning(false); }
  }

  async function retry(p: Post) {
    setRetrying(true);
    try {
      const np = await engine.socialRetry(p.id);
      setSel(np);
      notify("Đã thử đăng lại");
      await load();
    } catch (e) { const d = describeError(toEngineError(e)); notify(`${d.title}. ${d.detail}`); }
    finally { setRetrying(false); }
  }

  const projectDir = (p: Post) => p.project ? state.projects.find((x) => x.dir.replace(/\\/g, "/").split("/").pop() === p.project)?.dir ?? null : null;
  const chips = (p: Post) => p.channels.map(channelLabel).join(", ");

  const postBtn = (p: Post) => (
    <button key={p.id} className={"post" + (p.status === "POSTED" ? " done" : "")} aria-label={`Bài ${hhmm(p.postDate)} ${p.title}`}
      style={{ width: "100%", border: 0, borderLeft: `3px solid ${colorOf(p.status)}`, textAlign: "left", cursor: "pointer", fontFamily: "inherit" }}
      onClick={() => setSel(p)}>
      <span><b>{hhmm(p.postDate)}</b>{chips(p)}</span>
    </button>
  );

  return (
    <div className="view on">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
        <h1>Lịch đăng</h1>
        <div className="row">
          <span className="seg">
            <button className={mode === "week" ? "on" : ""} onClick={() => setMode("week")}>Lưới tuần</button>
            <button className={mode === "list" ? "on" : ""} onClick={() => setMode("list")}>Danh sách</button>
          </span>
          <button className="btn ghost" onClick={() => setOffset((o) => o - 1)}>← Tuần trước</button>
          <b style={{ fontSize: 14 }}>{title}</b>
          <button className="btn ghost" onClick={() => setOffset((o) => o + 1)}>Tuần sau →</button>
        </div>
      </div>
      <div className="sub">Video đã lên lịch và các routine tự động đăng.</div>
      <div className="banner" style={{ marginBottom: 16 }}>Lịch đăng chạy trên bundle.social, đăng đúng giờ kể cả khi tắt máy.</div>
      {error && <div className="errline" role="alert" style={{ marginBottom: 10 }}>{describeError(error).title}. {describeError(error).detail}</div>}
      {loading && <div className="hint" style={{ marginBottom: 8 }}>Đang tải…</div>}

      {mode === "week" ? (
        <div className="week">
          {days.map(({ label, d, ps, today }) => (
            <div key={label} className={"day" + (today ? " today" : "")} data-testid={`day-${label}`}>
              <h4>{label} {d.getDate()}/{d.getMonth() + 1}</h4>
              {ps.map((p) => postBtn(p))}
            </div>
          ))}
        </div>
      ) : (
        <div className="stack">
          {days.every((x) => x.ps.length === 0) && <div className="hint">Tuần này chưa có bài nào.</div>}
          {days.filter((x) => x.ps.length).map(({ label, d, ps }) => (
            <div key={label} className="card">
              <h3>{label} {d.getDate()}/{d.getMonth() + 1}</h3>
              {ps.map((p) => postBtn(p))}
            </div>
          ))}
        </div>
      )}

      {sel && (
        <div className="card" style={{ marginTop: 14 }} role="region" aria-label="Chi tiết bài đăng">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3 style={{ margin: 0 }}>{sel.title || "Bài đăng"}</h3>
            <button className="btn ghost" onClick={() => setSel(null)}>Đóng</button>
          </div>
          <div className="setgrid" style={{ marginTop: 8 }}>
            <span className="k">Giờ</span><span>{postTime(sel.postDate)}</span>
            <span className="k">Kênh</span><span>{chips(sel)}</span>
            <span className="k">Trạng thái</span>
            <span style={{ color: colorOf(sel.status), fontWeight: 600 }}>{STATUS_VI[sel.status] ?? sel.status}</span>
          </div>
          {sel.error && <div className="errline" style={{ marginTop: 8 }}>{sel.error}</div>}
          <div className="row" style={{ marginTop: 10, flexWrap: "wrap" }}>
            {Object.entries(sel.permalinks ?? {}).map(([t, url]) => (
              <button key={t} className="btn ghost" onClick={() => void openUrl(url)}>Xem trên {channelLabel(t)}</button>
            ))}
            {projectDir(sel) && <button className="btn ghost" onClick={() => go({ name: "project", dir: projectDir(sel)! })}>Mở project</button>}
            {sel.status === "ERROR" && <button className="btn primary" disabled={retrying} onClick={() => void retry(sel)}>Thử lại</button>}
          </div>
        </div>
      )}

      <RoutineEditor routines={settings?.routines ?? []} channels={channels} running={running}
        onChange={(r) => void saveRoutines(r)} onRunNow={() => void runNow()} />
    </div>
  );
}
