import { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import type { EngineJob } from "../lib/engine";
import DropZone from "../components/DropZone";
import ErrorPanel from "../components/ErrorPanel";
import { toEngineError, type AnyEngineError } from "../lib/errors";
import { nicheLabel } from "../lib/format";
import type { Card } from "../lib/types";
import { useStore } from "../state/store";

const baseName = (p: string) => p.split(/[\\/]/).pop() ?? p;

export default function NewVideo({ niche, dir: existingDir }: { niche: string; dir?: string }) {
  const { dispatch, go, refreshProjects, notify } = useStore();
  const [clip, setClip] = useState<string | null>(null);
  const [logo, setLogo] = useState<string | null>(null);
  const [music, setMusic] = useState<string | null>(null);
  const [dir, setDir] = useState<string | null>(existingDir ?? null);
  const [cards, setCards] = useState<Card[]>([]);
  const [picked, setPicked] = useState<number | null>(null);
  const [prompt, setPrompt] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [stepLabel, setStepLabel] = useState("");
  const [err, setErr] = useState<AnyEngineError | null>(null);
  const shown = useRef<string[]>([]);
  const job = useRef<EngineJob | null>(null);

  // Leaving the screen must not leave an analyze job burning a Claude turn.
  useEffect(() => () => { void job.current?.cancel(); }, []);

  async function runAnalyze(d: string, exclude: string[]) {
    setAnalyzing(true); setErr(null); setPicked(null); setStepLabel("");
    try {
      const got = await engine.analyze(d, exclude, (e) => { if (e.type === "step") setStepLabel(e.label); },
        (j) => { job.current = j; });
      shown.current = [...shown.current, ...got.map((c) => c.title)];
      setCards(got);
    } catch (e) {
      setErr(toEngineError(e));
    } finally {
      job.current = null;
      setAnalyzing(false);
    }
  }

  // Opened from an existing, not-yet-built project: reuse its clip, assets, prompt and saved card.
  useEffect(() => {
    if (!existingDir) return;
    let alive = true;
    (async () => {
      try {
        const d = await api.getProject(existingDir);
        if (!alive) return;
        setClip(d.clip); setLogo(d.logo); setMusic(d.music);
        if (d.scriptCard) {
          shown.current = [d.scriptCard.title];
          setCards([d.scriptCard]); setPicked(0);
          setPrompt(d.prompt || d.scriptCard.prompt);
        } else {
          setPrompt(d.prompt);
          await runAnalyze(existingDir, []);
        }
      } catch (e) { if (alive) setErr(toEngineError(e)); }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingDir]);

  async function onClip(path: string) {
    setClip(path); setCards([]); setErr(null); shown.current = [];
    try {
      const p = await api.createProject(niche, path, logo, music);
      setDir(p.dir);
      await refreshProjects();
      await runAnalyze(p.dir, []);
    } catch (e) {
      setClip(null);
      setErr(toEngineError(e));
    }
  }

  async function onAsset(kind: "logo" | "music", path: string) {
    (kind === "logo" ? setLogo : setMusic)(path);
    if (dir) {
      try { await api.setProjectAsset(dir, kind, path); } catch (e) { notify(toEngineError(e).message); }
    }
  }

  async function pick(i: number) {
    setPicked(i);
    setPrompt(cards[i].prompt);
    if (dir) { try { await api.updateProject(dir, { script_card: cards[i] }); } catch { /* non-fatal */ } }
  }

  const canBuild = !!dir && !analyzing && (prompt.trim() !== "" || picked !== null);

  async function build() {
    if (!dir) return;
    const text = prompt.trim();
    try {
      await api.updateProject(dir, { prompt: text });
    } catch (e) { notify(toEngineError(e).message); return; }
    dispatch({ type: "pendingEdit", pendingEdit: { dir, prompt: text } });
    go({ name: "project", dir });
  }

  return (
    <div className="view on">
      <div className="backrow">
        <button className="backbtn" onClick={() => go({ name: "niche" })}>← Đổi ngành</button>
        <h1 style={{ margin: 0 }}>Video mới</h1>
        <span className="catbadge">{nicheLabel(niche)}</span>
      </div>
      <div className="sub">Thả clip vào, AI gợi ý kịch bản, bạn chọn rồi bấm dựng.</div>
      <div className="newgrid">
        <div>
          {clip ? (
            <div className="clipcard">
              <div className="meta"><b>{baseName(clip)}</b><span className="muted">{clip}</span></div>
            </div>
          ) : (
            <DropZone kind="clip" variant="big" dragDrop accept={["mp4", "mov", "m4v"]} onFile={onClip}
              label="Kéo clip vào đây" hint="hoặc bấm để chọn file (mp4, mov)" />
          )}
        </div>
        <div>
          <div className="slots">
            <DropZone kind="logo" variant="slot" label="Logo (tùy chọn)" hint="PNG/JPG" accept={["png", "jpg", "jpeg"]}
              value={logo} onFile={(p) => onAsset("logo", p)} />
            <DropZone kind="music" variant="slot" label="Nhạc nền (tùy chọn)" hint="MP3/M4A/WAV" accept={["mp3", "m4a", "wav"]}
              value={music} onFile={(p) => onAsset("music", p)} />
          </div>
          <div className="scbar">
            <div className="label" style={{ margin: 0 }}>Kịch bản AI gợi ý</div>
            {cards.length > 0 && !analyzing && dir && (
              <button className="linkbtn" onClick={() => runAnalyze(dir, shown.current)}>↻ Gợi ý khác</button>
            )}
          </div>
          {analyzing && (
            <div className="sc-empty"><span className="spin" /> AI đang xem clip…{stepLabel && <div className="hint">{stepLabel}</div>}</div>
          )}
          {!analyzing && !clip && <div className="sc-empty">Chọn clip để AI gợi ý kịch bản</div>}
          {err && <div style={{ marginBottom: 8 }}><ErrorPanel compact error={err} onSettings={() => go({ name: "settings" })}
            onSetup={() => go({ name: "onboarding" })} onRetry={dir ? () => void runAnalyze(dir, shown.current) : undefined} /></div>}
          <div className="scripts">
            {cards.map((c, i) => (
              <div key={c.title + i} className={"sc" + (picked === i ? " on" : "")} role="button" tabIndex={0}
                onClick={() => pick(i)} onKeyDown={(e) => { if (e.key === "Enter") pick(i); }}>
                <div>
                  <b>{c.title}</b>
                  <span className="hk">{c.hook}</span>
                  <small>{c.outline}</small>
                </div>
              </div>
            ))}
          </div>
          <div className="label" style={{ marginTop: 10 }}>Mô tả muốn dựng</div>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)}
            placeholder="Ví dụ: làm ngắn gọn, mở đầu bằng câu chốt giá" />
          <div className="buildrow">
            <button className="btn primary big" disabled={!canBuild} onClick={build}>Dựng video</button>
            <span className="hint">{dir ? "" : "Chọn clip để bắt đầu"}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
