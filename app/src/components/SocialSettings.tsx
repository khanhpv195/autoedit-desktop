import { useCallback, useEffect, useRef, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { toEngineError } from "../lib/errors";
import { V2_CHANNELS, channelLabel } from "../lib/format";
import type { SocialAccount } from "../lib/types";
import { useStore } from "../state/store";

const ICON: Record<string, string> = { TIKTOK: "Tt", INSTAGRAM: "Ig", YOUTUBE: "Yt", FACEBOOK: "Fb" };

export default function SocialSettings({ onConnected }: { onConnected?: (connected: boolean) => void }) {
  const { state, dispatch, notify } = useStore();
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const account = state.social;
  const settings = state.settings;
  // Always save on top of the newest settings, never a copy captured by an older render.
  const latest = useRef(settings);
  latest.current = settings;

  const selectTeam = useCallback(async (id: string) => {
    const cur = latest.current;
    if (!cur) return;
    const next = { ...cur, socialTeamId: id };
    dispatch({ type: "settings", settings: next });
    try { await api.saveSettings(next); } catch (e) { notify(toEngineError(e).message); }
  }, [dispatch, notify]);

  const load = useCallback(async (): Promise<boolean> => {
    setBusy(true);
    setErr(null);
    try {
      const acc: SocialAccount = await engine.socialCheck();
      dispatch({ type: "social", social: acc });
      onConnected?.(true);
      const fresh = latest.current;
      const cur = fresh?.socialTeamId;
      if (fresh && acc.teams.length > 0 && !acc.teams.some((t) => t.id === cur)) {
        const next = { ...fresh, socialTeamId: acc.teams[0].id };
        dispatch({ type: "settings", settings: next });
        await api.saveSettings(next);
      }
      return true;
    } catch (e) {
      const x = toEngineError(e);
      if (x.code === "SOCIAL_AUTH") {
        setErr("Key không đúng");
        try { await api.clearSocialKey(); } catch { /* keep the message */ }
        dispatch({ type: "socialKey", has: false });
        onConnected?.(false);
      } else {
        setErr(x.message || "Không kết nối được bundle.social");
      }
      return false;
    } finally { setBusy(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch, settings?.socialTeamId, !!settings]);

  // A stored key: read the account once when this panel opens.
  useEffect(() => {
    if (state.hasSocialKey && !state.social) void load();
    else if (state.hasSocialKey) onConnected?.(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.hasSocialKey]);

  async function submit() {
    const k = key.trim();
    if (!k) return;
    setKey("");
    setErr(null);
    try { await api.setSocialKey(k); } catch (e) { setErr(toEngineError(e).message); return; }
    dispatch({ type: "socialKey", has: true });
    await load();
  }

  async function remove() {
    try { await api.clearSocialKey(); } catch (e) { notify(toEngineError(e).message); return; }
    dispatch({ type: "socialKey", has: false });
    onConnected?.(false);
  }

  async function portal(team: string) {
    try { await openUrl(await engine.socialPortal(team)); }
    catch (e) { notify(toEngineError(e).message); }
  }

  if (!state.hasSocialKey) {
    return (
      <div className="card" id="bsCard">
        <h3>Đăng bài bundle.social</h3>
        <div className="hint" style={{ marginBottom: 10 }}>Dán key để đăng và lên lịch video lên TikTok, Instagram, YouTube, Facebook.</div>
        <div className="row">
          <input type="password" value={key} placeholder="Dán API key bundle.social" aria-label="API key bundle.social"
            autoComplete="off" onChange={(e) => setKey(e.target.value)} />
          <button className="btn ghost" disabled={busy || !key.trim()} onClick={submit}>{busy ? "Đang kiểm tra…" : "Kiểm tra"}</button>
        </div>
        {err && <div className="errline" style={{ marginTop: 8 }}>{err}</div>}
      </div>
    );
  }

  const team = account?.teams.find((t) => t.id === settings?.socialTeamId) ?? account?.teams[0];
  return (
    <div className="card" id="bsCard">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>Đăng bài bundle.social</h3>
        <span className="row">
          <button className="btn ghost" disabled={busy} onClick={() => void load()}>↻ Làm mới</button>
          <button className="btn ghost" onClick={remove}>Gỡ key</button>
        </span>
      </div>
      {err && <div className="errline" style={{ marginBottom: 8 }}>{err}</div>}
      {!account && !err && <div className="hint">Đang đọc tài khoản…</div>}
      {account && (
        <div className="stack">
          <div className="setgrid">
            <span className="k">Tài khoản</span><span><span className="pill ok">✓ Đã kết nối</span> <b>{account.organization.name}</b></span>
            <span className="k">Bài đăng</span>
            <span>Đã đăng {account.usage.posts.used}/{account.usage.posts.limit} bài tháng này</span>
            <span className="k">Tải lên</span><span>Đã tải {account.usage.uploads.used}/{account.usage.uploads.limit}</span>
            <span className="k">Team</span>
            <span>
              {account.teams.length > 1 ? (
                <select aria-label="Team" value={team?.id ?? ""} onChange={(e) => void selectTeam(e.target.value)}>
                  {account.teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              ) : (team?.name ?? "Chưa có team")}
            </span>
          </div>
          <div>
            <div className="label">Kênh đã nối</div>
            <div className="chans">
              {team?.channels.length === 0 && <span className="hint">Chưa nối kênh nào.</span>}
              {team?.channels.map((c, i) => {
                const ok = V2_CHANNELS.includes(c.type);
                return (
                  <span key={c.type + i} className={"ch" + (ok ? "" : " off")} title={ok ? "" : "chưa hỗ trợ đăng video"}>
                    <b>{ICON[c.type] ?? c.type.slice(0, 2)}</b> {c.name || channelLabel(c.type)}
                    {c.username ? <span className="hint"> @{c.username.replace(/^@/, "")}</span> : null}
                    {!ok && <span className="hint"> chưa hỗ trợ đăng video</span>}
                  </span>
                );
              })}
            </div>
            {team && <button className="btn ghost" onClick={() => void portal(team.id)}>＋ Thêm / quản lý kênh</button>}
          </div>
        </div>
      )}
    </div>
  );
}
