import { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { openUrl } from "@tauri-apps/plugin-opener";

type Phase = "idle" | "waiting" | "checking";

/** Claude login via the CLI PTY (browser OAuth), plus the API key fallback. */
export default function ClaudeLogin({ cliPath, onConnected }: { cliPath: string | null; onConnected: (source: string) => void }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [lines, setLines] = useState<string[]>([]);
  const [url, setUrl] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [keyOpen, setKeyOpen] = useState(false);
  const [key, setKey] = useState("");
  const onConnectedRef = useRef(onConnected);
  onConnectedRef.current = onConnected;

  useEffect(() => {
    let alive = true;
    const unsubs: Array<() => void> = [];
    (async () => {
      const a = await api.onLoginOutput((o) => {
        setLines((l) => [...l.slice(-30), o.line]);
        if (o.url) setUrl(o.url);
      });
      const b = await api.onLoginDone(async (d) => {
        if (!d.ok) { setPhase("idle"); setError(d.error || "Đăng nhập không thành công"); return; }
        setPhase("checking");
        try { onConnectedRef.current(await engine.authCheck()); }
        catch (e) { setPhase("idle"); setError(errMsg(e)); }
      });
      if (alive) unsubs.push(...[a, b].filter((f): f is () => void => typeof f === "function"));
      else [a, b].forEach((f) => typeof f === "function" && f());
    })();
    return () => { alive = false; unsubs.forEach((f) => f()); };
  }, []);

  async function start() {
    if (!cliPath) return;
    setError(null); setLines([]); setUrl(null); setCode(""); setPhase("waiting");
    try { await api.loginStart(cliPath); }
    catch (e) { setPhase("idle"); setError(errMsg(e)); }
  }
  async function cancel() {
    try { await api.loginCancel(); } catch { /* ignore */ }
    setPhase("idle");
  }
  async function sendCode() {
    const t = code.trim();
    if (!t) return;
    setCode("");
    try { await api.loginInput(t); } catch (e) { setError(errMsg(e)); }
  }
  async function saveKey() {
    const k = key.trim();
    if (!k) return;
    setKey("");
    setError(null);
    try {
      await api.setApiKey(k);
      onConnected(await engine.authCheck());
    } catch (e) { setError(errMsg(e)); }
  }

  return (
    <div>
      {phase === "idle" && (
        <button className="btn dark" onClick={start} disabled={!cliPath}>Đăng nhập Claude</button>
      )}
      {phase !== "idle" && (
        <div>
          <div className="row">
            <span className="spin" />
            <span style={{ fontSize: 14 }}>
              {phase === "checking" ? "Đang kiểm tra kết nối…" : "Đã mở trình duyệt. Đăng nhập tài khoản Claude và bấm Authorize…"}
            </span>
          </div>
          {lines.length > 0 && <div className="mono" style={{ marginTop: 10 }}>{lines.join("\n")}</div>}
          {url && (
            <div style={{ marginTop: 10 }}>
              <button className="btn ghost" onClick={() => openUrl(url)}>Mở trang đăng nhập</button>
            </div>
          )}
          <div className="row" style={{ marginTop: 10 }}>
            <input type="text" value={code} placeholder="Dán mã từ trình duyệt" aria-label="Dán mã từ trình duyệt"
              onChange={(e) => setCode(e.target.value)} />
            <button className="btn ghost" onClick={sendCode}>Gửi</button>
          </div>
          <div className="hint" style={{ marginTop: 8 }}>
            <button className="linka" onClick={cancel}>Hủy</button>
          </div>
        </div>
      )}
      {error && <div className="errline">{error}</div>}
      <div className="hint" style={{ marginTop: 10 }}>
        Máy đã đăng nhập Claude Code thì app tự nhận. ·{" "}
        <button className="linka" onClick={() => setKeyOpen((v) => !v)}>Dùng API key thay thế</button>
      </div>
      {keyOpen && (
        <div className="row" style={{ marginTop: 10 }}>
          <input type="password" value={key} placeholder="sk-ant-api03-…" aria-label="API key" autoComplete="off"
            onChange={(e) => setKey(e.target.value)} />
          <button className="btn ghost" onClick={saveKey}>Lưu</button>
        </div>
      )}
    </div>
  );
}

function errMsg(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  if (e && typeof e === "object" && "message" in e) return String((e as { message: unknown }).message);
  return "Có lỗi xảy ra";
}
