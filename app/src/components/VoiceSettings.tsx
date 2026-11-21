import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { describeError, toEngineError } from "../lib/errors";
import type { ElevenStatus, Voice } from "../lib/types";
import { useStore } from "../state/store";

const errText = (e: unknown) => {
  const x = toEngineError(e);
  const d = describeError(x);
  return x.code === "AGENT_FAILED" ? x.message : d.title;
};

/** "Lồng tiếng (ElevenLabs)": key, remaining characters, voice list with preview, default voice. */
export default function VoiceSettings() {
  const { state, dispatch, notify } = useStore();
  const [status, setStatus] = useState<ElevenStatus | null>(null);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  // Always save on top of the newest settings, never a copy captured by an older render.
  const latest = useRef(state.settings);
  latest.current = state.settings;

  const loadVoices = useCallback(async () => {
    try { setVoices((await api.elevenVoices()) ?? []); } catch (e) { setErr(errText(e)); }
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const s = await api.elevenStatus();
        if (!alive) return;
        setStatus(s ?? { hasKey: false });
        if (s?.hasKey) await loadVoices();
      } catch { if (alive) setStatus({ hasKey: false }); }
    })();
    return () => { alive = false; };
  }, [loadVoices]);

  async function submit() {
    const k = key.trim();
    if (!k) return;
    setBusy(true); setErr(null);
    try {
      const r = await api.setElevenKey(k);
      setKey("");
      setStatus({ hasKey: true, remaining: r?.remaining });
      await loadVoices();
    } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  }

  async function remove() {
    try { await api.clearElevenKey(); } catch (e) { notify(toEngineError(e).message); return; }
    const cur = latest.current;
    if (cur) dispatch({ type: "settings", settings: { ...cur, voiceId: null, voiceName: null } });
    setStatus({ hasKey: false }); setVoices([]); setErr(null);
  }

  async function choose(v: Voice) {
    const cur = latest.current;
    if (!cur) return;
    const next = { ...cur, voiceId: v.id, voiceName: v.name };
    dispatch({ type: "settings", settings: next });
    try { await api.saveSettings(next); } catch (e) { notify(toEngineError(e).message); }
  }

  function preview(url: string) {
    const a = audio.current;
    if (!a) return;
    a.src = url;
    const p = a.play();
    if (p) p.catch(() => notify("Không phát được bản nghe thử"));
  }

  if (!status?.hasKey) {
    return (
      <div className="card">
        <h3>Lồng tiếng (ElevenLabs)</h3>
        <div className="hint" style={{ marginBottom: 10 }}>Dán API key ElevenLabs để AI lồng tiếng cho video không có lời. Ký tự tính vào tài khoản ElevenLabs của bạn.</div>
        <div className="row">
          <input type="password" value={key} placeholder="Dán API key ElevenLabs" aria-label="API key ElevenLabs"
            autoComplete="off" onChange={(e) => setKey(e.target.value)} />
          <button className="btn ghost" aria-label="Lưu key ElevenLabs" disabled={busy || !key.trim()} onClick={submit}>
            {busy ? "Đang kiểm tra…" : "Lưu"}
          </button>
        </div>
        {err && <div className="errline" style={{ marginTop: 8 }}>{err}</div>}
      </div>
    );
  }

  const chosen = state.settings?.voiceId ?? null;
  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>Lồng tiếng (ElevenLabs)</h3>
        <button className="btn ghost" onClick={remove}>Xóa key</button>
      </div>
      <div className="row" style={{ marginBottom: 8 }}>
        <span className="pill ok">✓ Đã lưu key</span>
        {status.remaining !== undefined && <span>Còn {status.remaining.toLocaleString("vi-VN")} ký tự</span>}
      </div>
      {err && <div className="errline" style={{ marginBottom: 8 }}>{err}</div>}
      <div className="label">Giọng đọc</div>
      {voices.length === 0 && !err && <div className="hint">Đang tải danh sách giọng…</div>}
      <div className="stack">
        {voices.map((v) => (
          <div key={v.id} className="row" style={{ justifyContent: "space-between" }}>
            <span className="row">
              <button className="btn ghost" aria-label={`Nghe thử ${v.name}`} disabled={!v.previewUrl}
                onClick={() => v.previewUrl && preview(v.previewUrl)}>▶</button>
              <b>{v.name}</b>
              {Object.values(v.labels).length > 0 && <span className="hint">{Object.values(v.labels).join(" · ")}</span>}
            </span>
            {chosen === v.id
              ? <span className="pill ok">✓ Mặc định</span>
              : <button className="btn ghost" onClick={() => void choose(v)}>Chọn làm mặc định</button>}
          </div>
        ))}
      </div>
      <audio ref={audio} hidden />
    </div>
  );
}
