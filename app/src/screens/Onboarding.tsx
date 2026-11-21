import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import ClaudeLogin from "../components/ClaudeLogin";
import SocialSettings from "../components/SocialSettings";
import { useStore } from "../state/store";

const pct = (p: number) => Math.round(Math.max(0, Math.min(1, p)) * 100);
const msg = (e: unknown) => (e instanceof Error ? e.message : typeof e === "string" ? e : "Có lỗi xảy ra");

export default function Onboarding() {
  const { state, dispatch, refreshProjects, go } = useStore();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [cliP, setCliP] = useState(0);
  const [cliLabel, setCliLabel] = useState("");
  const [cliErr, setCliErr] = useState<string | null>(null);
  const [cliTry, setCliTry] = useState(0);
  const [source, setSource] = useState<string | null>(null);
  const [modelP, setModelP] = useState(0);
  const [modelDone, setModelDone] = useState(false);
  const [modelErr, setModelErr] = useState<string | null>(null);
  const [modelTry, setModelTry] = useState(0);
  const [socialOk, setSocialOk] = useState(false);
  const [cli, setCli] = useState<string | null>(null);
  const cliStarted = useRef(-1);
  const modelStarted = useRef(-1);

  // step 1: download Claude CLI
  useEffect(() => {
    if (cliStarted.current === cliTry) return;
    cliStarted.current = cliTry;
    setCliErr(null);
    engine.setupCli((p, label) => { setCliP(p); setCliLabel(label); })
      .then((path) => { setCli(path); dispatch({ type: "cliPath", cliPath: path }); setStep(2); })
      .catch((e) => setCliErr(msg(e)));
  }, [cliTry, dispatch]);

  // model download in the background once the CLI is ready
  useEffect(() => {
    if (!cli || modelStarted.current === modelTry) return;
    modelStarted.current = modelTry;
    setModelErr(null);
    engine.setupModel(setModelP).then(() => setModelDone(true)).catch((e) => setModelErr(msg(e)));
  }, [cli, modelTry]);

  // step 2: existing login?
  useEffect(() => {
    if (step !== 2) return;
    api.authStatus().then((s) => { if (s?.source) setSource(s.source); }).catch(() => {});
  }, [step]);

  const connected = useCallback((s: string) => { setSource(s); dispatch({ type: "auth", auth: s }); }, [dispatch]);

  async function begin() {
    const settings = { model: "claude-sonnet-5-5", projectsRoot: "", lastNiche: null, ...(state.settings ?? {}), onboarded: true };
    await api.saveSettings(settings);
    dispatch({ type: "settings", settings });
    await refreshProjects();
    go({ name: "niche" });
  }

  return (
    <div className="view on">
      <div className="onb">
        <div className="stepn"><span className="on" /><span className={step >= 2 ? "on" : ""} /><span className={step === 3 ? "on" : ""} /></div>
        <h1>Chào mừng đến AutoEdit</h1>
        <div className="sub"><b>1 Tải Claude</b> · <b>2 Đăng nhập Claude</b> · <b>3 Đăng bài (tùy chọn)</b></div>

        {step === 1 && (
          <div className="card">
            <h3>Bước 1 · Tải Claude</h3>
            {cliErr ? (
              <>
                <div className="errline">{cliErr}</div>
                <button className="btn primary" style={{ marginTop: 12 }} onClick={() => setCliTry((n) => n + 1)}>Thử lại</button>
              </>
            ) : (
              <>
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
                  <span style={{ fontSize: 14 }}>{cliLabel || "Đang chuẩn bị…"}</span>
                  <span className="hint">{pct(cliP)}%</span>
                </div>
                <div className="bar"><i style={{ width: pct(cliP) + "%" }} /></div>
                <div className="hint" style={{ marginTop: 8 }}>~160MB, chỉ tải một lần</div>
              </>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="stack">
            <div className="card">
              <h3>Bước 2 · Đăng nhập Claude</h3>
              {source ? (
                <div className="row">
                  <span className="pill ok">✓ Đã kết nối · {source === "api-key" ? "API key" : "subscription"}</span>
                </div>
              ) : (
                <>
                  <div className="sub" style={{ margin: "0 0 12px" }}>Dùng tài khoản Claude Pro hoặc Max của bạn. App mở trình duyệt để bạn đăng nhập.</div>
                  <ClaudeLogin cliPath={cli} onConnected={connected} />
                </>
              )}
            </div>
            <div className="card">
              <h3>Model giọng nói</h3>
              {modelDone ? (
                <span className="okline">✓ Đã tải xong</span>
              ) : modelErr ? (
                <>
                  <div className="errline">{modelErr}</div>
                  <button className="btn ghost" style={{ marginTop: 10 }} onClick={() => setModelTry((n) => n + 1)}>Thử lại</button>
                </>
              ) : (
                <>
                  <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
                    <span style={{ fontSize: 14 }}>Đang tải model giọng nói… {pct(modelP)}%, ~1.5GB</span>
                  </div>
                  <div className="bar"><i style={{ width: pct(modelP) + "%" }} /></div>
                </>
              )}
            </div>
            <div style={{ textAlign: "right" }}>
              <button className="btn primary big" disabled={!source || !modelDone} onClick={() => setStep(3)}>Bắt đầu</button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="stack">
            <div className="card">
              <h3>Bước 3 · Đăng bài (tùy chọn)</h3>
              <div className="sub" style={{ margin: "0 0 12px" }}>Nối bundle.social để đăng video thẳng lên TikTok, Instagram, YouTube, Facebook. Có thể làm sau trong Cài đặt.</div>
            </div>
            <SocialSettings onConnected={setSocialOk} />
            <div style={{ textAlign: "right" }}>
              <button className="btn primary big" onClick={begin}>{socialOk ? "Hoàn tất" : "Bỏ qua"}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
