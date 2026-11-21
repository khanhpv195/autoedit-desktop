import { useCallback, useEffect, useState } from "react";
import ClaudeLogin from "../components/ClaudeLogin";
import McpSettings from "../components/McpSettings";
import SocialSettings from "../components/SocialSettings";
import VoiceSettings from "../components/VoiceSettings";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { DEFAULT_CTA, DEFAULT_LENGTH, LENGTHS, ctaValid } from "../lib/defaults";
import { describeError, toEngineError } from "../lib/errors";
import type { AuthSource, Settings as SettingsT } from "../lib/types";
import { useStore } from "../state/store";

type Tab = "gen" | "conn" | "agent";
const TABS: [Tab, string][] = [["gen", "Chung"], ["conn", "Kết nối & MCP"], ["agent", "AI dựng"]];
const MODELS: [string, string][] = [
  ["claude-sonnet-5-5", "Sonnet 5.5 — cân bằng (mặc định)"],
  ["claude-opus-5-5", "Opus 5.5 — tốt nhất, tốn nhiều lượt nhất"],
  ["claude-haiku-5-5", "Haiku 5.5 — rẻ nhất, dựng kém hơn với clip khó"],
];
const SOURCE_LABEL: Record<string, string> = {
  "app-token": "Subscription Claude · token app",
  "claude-code": "Subscription Claude · Claude Code trên máy",
  "api-key": "API key",
};

export default function Settings() {
  const { state, dispatch, notify, refreshProjects } = useStore();
  const [tab, setTab] = useState<Tab>(state.route.name === "settings" && state.route.tab ? state.route.tab : "gen");
  const [source, setSource] = useState<AuthSource | undefined>(undefined);
  const [changing, setChanging] = useState(false);
  const [key, setKey] = useState("");
  const settings = state.settings;

  const refreshAuth = useCallback(async () => {
    try { const s = await api.authStatus(); setSource(s?.source ?? null); } catch { setSource(null); }
  }, []);
  useEffect(() => { void refreshAuth(); }, [refreshAuth]);

  async function save(next: SettingsT) {
    dispatch({ type: "settings", settings: next });
    try {
      await api.saveSettings(next);
      if (settings && next.projectsRoot !== settings.projectsRoot) await refreshProjects();
    } catch (e) { notify(toEngineError(e).message); }
  }

  async function changeFolder() {
    const p = await api.pickFolder();
    if (p && settings) await save({ ...settings, projectsRoot: p });
  }

  async function startChange() {
    if (!state.cliPath) {
      try { dispatch({ type: "cliPath", cliPath: await engine.setupCli() }); }
      catch (e) { notify(toEngineError(e).message); return; }
    }
    setChanging(true);
  }

  async function doLogout() {
    try { await api.logout(); } catch (e) { notify(toEngineError(e).message); }
    await refreshAuth();
  }

  async function saveKey() {
    const k = key.trim();
    if (!k) return;
    setKey("");
    try { await api.setApiKey(k); notify("Đã lưu API key"); } catch (e) { notify(toEngineError(e).message); }
    await refreshAuth();
  }

  async function removeKey() {
    try { await api.clearApiKey(); notify("Đã xóa API key"); } catch (e) { notify(toEngineError(e).message); }
    await refreshAuth();
  }

  async function check() {
    try { await engine.authCheck(); notify("✓ Kết nối Claude hoạt động"); }
    catch (e) { const d = describeError(toEngineError(e)); notify(`${d.title}. ${d.detail}`); }
  }

  const status = source === undefined ? "Đang kiểm tra…" : source ? SOURCE_LABEL[source] : "Chưa kết nối";

  return (
    <div className="view on">
      <div className="set-wrap">
        <h1>Cài đặt</h1>
        <div className="stabs" style={{ marginTop: 12 }}>
          {TABS.map(([id, label]) => (
            <div key={id} className={"stab" + (tab === id ? " on" : "")} role="tab" aria-selected={tab === id} tabIndex={0}
              onClick={() => setTab(id)} onKeyDown={(e) => { if (e.key === "Enter") setTab(id); }}>{label}</div>
          ))}
        </div>

        {tab === "gen" && (
          <div className="tabp stack">
            <div className="card">
              <h3>Máy & lưu trữ</h3>
              <div className="setgrid">
                <span className="k">Thư mục project</span>
                <span className="row">
                  <code style={{ fontSize: 12 }}>{settings?.projectsRoot}</code>
                  <button className="btn ghost" style={{ padding: "6px 10px" }} onClick={changeFolder}>Đổi…</button>
                </span>
              </div>
            </div>
            {settings && <DefaultsCard settings={settings} save={save} />}
          </div>
        )}

        {tab === "conn" && (
          <div className="tabp stack">
            <SocialSettings />
            <VoiceSettings />
            <McpSettings />
          </div>
        )}

        {tab === "agent" && (
          <div className="tabp stack">
            <div className="card">
              <h3>Tài khoản Claude</h3>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span className={"pill " + (source ? "ok" : "warn")}>{status}</span>
                <span className="row">
                  <button className="btn ghost" onClick={startChange}>Đổi tài khoản</button>
                  {source === "app-token" && <button className="btn ghost" onClick={doLogout}>Đăng xuất</button>}
                  <button className="btn ghost" onClick={check}>Kiểm tra kết nối</button>
                </span>
              </div>
              {changing && (
                <div style={{ marginTop: 14 }}>
                  <ClaudeLogin cliPath={state.cliPath} onConnected={(s) => {
                    dispatch({ type: "auth", auth: s }); setChanging(false); void refreshAuth(); notify("✓ Đã kết nối Claude");
                  }} />
                </div>
              )}
              <div className="hint" style={{ marginTop: 8 }}>Dùng lượt của gói Claude, không tính tiền theo video.</div>
            </div>
            <div className="card">
              <h3>API key</h3>
              <div className="row">
                <input type="password" value={key} placeholder="sk-ant-api03-…" aria-label="API key" autoComplete="off"
                  onChange={(e) => setKey(e.target.value)} />
                <button className="btn ghost" onClick={saveKey}>Lưu</button>
                <button className="btn ghost" onClick={removeKey}>Xóa API key</button>
              </div>
            </div>
            <div className="card">
              <h3>Model</h3>
              <select aria-label="Model" value={settings?.model || MODELS[0][0]}
                onChange={(e) => settings && save({ ...settings, model: e.target.value })}>
                {MODELS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
              </select>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** "Mặc định cho video mới": logo, CTA and target length that New Video starts with. */
function DefaultsCard({ settings, save }: { settings: SettingsT; save: (s: SettingsT) => Promise<void> }) {
  const { dispatch, notify } = useStore();
  const [cta, setCta] = useState(settings.defaultCta ?? DEFAULT_CTA);
  const [ctaErr, setCtaErr] = useState(false);
  const length = settings.defaultLength ?? DEFAULT_LENGTH;

  async function saveCta() {
    if (!ctaValid(cta)) { setCtaErr(true); return; }
    setCtaErr(false);
    const t = cta.trim();
    setCta(t);
    if (t !== (settings.defaultCta ?? DEFAULT_CTA)) await save({ ...settings, defaultCta: t });
  }

  async function pickLogo() {
    const p = await api.pickFile("logo");
    if (!p) return;
    try { dispatch({ type: "settings", settings: await api.setDefaultLogo(p) }); }
    catch (e) { notify(toEngineError(e).message); }
  }

  async function removeLogo() {
    try { dispatch({ type: "settings", settings: await api.clearDefaultLogo() }); }
    catch (e) { notify(toEngineError(e).message); }
  }

  return (
    <div className="card">
      <h3>Mặc định cho video mới</h3>
      <div className="setgrid">
        <span className="k">Logo mặc định</span>
        <span className="row">
          {settings.defaultLogo && (
            <img src={api.fileSrc(settings.defaultLogo)} alt="Logo mặc định" style={{ height: 40, maxWidth: 120, objectFit: "contain" }} />
          )}
          <button className="btn ghost" style={{ padding: "6px 10px" }} onClick={pickLogo}>
            {settings.defaultLogo ? "Đổi logo" : "Chọn logo"}
          </button>
          {settings.defaultLogo && <button className="btn ghost" style={{ padding: "6px 10px" }} onClick={removeLogo}>Bỏ logo</button>}
        </span>
        <span className="k">Chữ kêu gọi</span>
        <span>
          <span className="row">
            <input value={cta} aria-label="Chữ kêu gọi mặc định" maxLength={60} aria-invalid={ctaErr}
              onChange={(e) => setCta(e.target.value)} onBlur={() => void saveCta()} />
            <button className="btn ghost" aria-label="Lưu chữ kêu gọi" onClick={() => void saveCta()}>Lưu</button>
          </span>
          {ctaErr && <div className="errline" style={{ marginTop: 6 }}>Chữ kêu gọi cần 1–30 ký tự</div>}
        </span>
        <span className="k">Độ dài video</span>
        <span className="row">
          {LENGTHS.map(([id, label]) => (
            <button key={id} className={"chip" + (length === id ? " on" : "")} aria-pressed={length === id}
              onClick={() => { if (id !== length) void save({ ...settings, defaultLength: id }); }}>{label}</button>
          ))}
        </span>
      </div>
    </div>
  );
}
