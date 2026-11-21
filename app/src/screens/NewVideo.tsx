import { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import type { EngineJob } from "../lib/engine";
import DropZone from "../components/DropZone";
import ErrorPanel from "../components/ErrorPanel";
import { toEngineError, type AnyEngineError } from "../lib/errors";
import { nicheLabel } from "../lib/format";
import { MAX_CLIPS, MAX_IMAGES, type Classified } from "../lib/media";
import type { Card } from "../lib/types";
import { useStore } from "../state/store";

const baseName = (p: string) => p.split(/[\\/]/).pop() ?? p;
type Media = { clips: string[]; images: string[] };

export default function NewVideo({ niche, dir: existingDir }: { niche: string; dir?: string }) {
  const { dispatch, go, refreshProjects, notify } = useStore();
  const [media, setMediaState] = useState<Media>({ clips: [], images: [] });
  const mediaRef = useRef<Media>(media);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const dirRef = useRef<string | null>(existingDir ?? null);
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
        setMedia({ clips: d.clips, images: d.images }); setLogo(d.logo); setMusic(d.music);
        if (d.scriptCard) {
          shown.current = [d.scriptCard.title];
          setCards([d.scriptCard]); setPicked(0);
          setPrompt(d.prompt || d.scriptCard.prompt);
        } else {
          setPrompt(d.prompt);
        }
      } catch (e) { if (alive) setErr(toEngineError(e)); }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingDir]);

  function setMedia(m: Media) { mediaRef.current = m; setMediaState(m); }

  /** Apply a media change: update the UI now, then sync to the project (serialized, latest state wins). */
  function changeMedia(next: Media) {
    setMedia(next);
    setCards([]); setPicked(null); setErr(null); shown.current = [];
    queue.current = queue.current.then(async () => {
      const sent = mediaRef.current;
      try {
        let d = dirRef.current;
        let detail;
        if (!d) {
          if (sent.clips.length === 0) return; // images wait for the first clip
          const p = await api.createProject(niche, sent.clips, sent.images, logo, music);
          d = p.dir; dirRef.current = d; setDir(d);
          await refreshProjects();
          detail = await api.getProject(d);
        } else {
          detail = await api.setProjectMedia(d, sent.clips, sent.images);
        }
        // Switch to the project's own copies, unless the user changed things meanwhile.
        if (mediaRef.current === sent) setMedia({ clips: detail.clips, images: detail.images });
      } catch (e) {
        if (!dirRef.current) setMedia({ clips: [], images: mediaRef.current.images });
        setErr(toEngineError(e));
      }
    });
  }

  function addMedia(c: Classified) {
    const cur = mediaRef.current;
    const clips = [...cur.clips, ...c.clips.filter((p) => !cur.clips.includes(p))];
    const images = [...cur.images, ...c.images.filter((p) => !cur.images.includes(p))];
    if (clips.length > MAX_CLIPS) notify(`Tối đa ${MAX_CLIPS} clip, đã bỏ bớt phần dư`);
    if (images.length > MAX_IMAGES) notify(`Tối đa ${MAX_IMAGES} ảnh, đã bỏ bớt phần dư`);
    const next = { clips: clips.slice(0, MAX_CLIPS), images: images.slice(0, MAX_IMAGES) };
    if (next.clips.length === cur.clips.length && next.images.length === cur.images.length) return;
    changeMedia(next);
  }

  function moveClip(i: number, d: -1 | 1) {
    const clips = [...mediaRef.current.clips];
    const j = i + d;
    if (j < 0 || j >= clips.length) return;
    [clips[i], clips[j]] = [clips[j], clips[i]];
    changeMedia({ ...mediaRef.current, clips });
  }
  const removeClip = (i: number) => {
    if (mediaRef.current.clips.length <= 1) return;
    changeMedia({ ...mediaRef.current, clips: mediaRef.current.clips.filter((_, k) => k !== i) });
  };
  const removeImage = (i: number) =>
    changeMedia({ ...mediaRef.current, images: mediaRef.current.images.filter((_, k) => k !== i) });

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
      <div className="sub">Thả clip và ảnh vào, bấm để AI gợi ý kịch bản (hoặc tự viết), rồi bấm dựng.</div>
      <div className="newgrid">
        <div>
          {media.clips.length === 0 && media.images.length === 0 ? (
            <DropZone kind="clip" variant="big" dragDrop onMedia={addMedia}
              label="Kéo clip và ảnh vào đây" hint="mp4, mov, png, jpg — chọn được nhiều file" />
          ) : (
            <>
              {media.clips.length > 0 ? (
                <div className="medialist">
                  {media.clips.map((c, i) => (
                    <div className="row" key={i}>
                      <span className="nm" title={c}>{i + 1}. {baseName(c)}</span>
                      <button aria-label={`Lên ${baseName(c)}`} disabled={i === 0} onClick={() => moveClip(i, -1)}>↑</button>
                      <button aria-label={`Xuống ${baseName(c)}`} disabled={i === media.clips.length - 1} onClick={() => moveClip(i, 1)}>↓</button>
                      <button aria-label={`Xóa ${baseName(c)}`} disabled={media.clips.length <= 1} onClick={() => removeClip(i)}>✕</button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="sc-empty">Thêm ít nhất 1 clip video để bắt đầu</div>
              )}
              {media.images.length > 0 && (
                <div className="imgstrip">
                  {media.images.map((im, i) => (
                    <div className="imgchip" key={i} title={im}>
                      <span>{baseName(im)}</span>
                      <button aria-label={`Xóa ảnh ${baseName(im)}`} onClick={() => removeImage(i)}>✕</button>
                    </div>
                  ))}
                </div>
              )}
              <DropZone kind="clip" variant="bar" dragDrop onMedia={addMedia} label="+ Thêm file" hint="kéo thả hoặc bấm để chọn" />
            </>
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
          {!analyzing && cards.length === 0 && (
            <div className="sc-empty">
              <button className="btn" disabled={!dir} onClick={() => dir && void runAnalyze(dir, [])}>✨ AI gợi ý kịch bản</button>
              {!dir && <div className="hint">Thêm clip để AI gợi ý</div>}
            </div>
          )}
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
            <span className="hint">{dir ? "" : "Thêm clip để bắt đầu"}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
