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
  const [logo, setLogoState] = useState<string | null>(null);
  const [music, setMusicState] = useState<string | null>(null);
  const logoRef = useRef<string | null>(null);
  const musicRef = useRef<string | null>(null);
  const [pending, setPending] = useState(0);
  const syncFailed = useRef(false);
  const gen = useRef(0);
  const srcToInput = useRef(new Map<string, string>());
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

  function setAsset(kind: "logo" | "music", v: string | null) {
    if (kind === "logo") { logoRef.current = v; setLogoState(v); } else { musicRef.current = v; setMusicState(v); }
  }

  /** Wait until every queued project sync has finished; returns the project dir (null when none exists yet). */
  async function settle(): Promise<string | null> {
    let q: Promise<void>;
    do { q = queue.current; await q; } while (q !== queue.current);
    return dirRef.current;
  }

  async function runAnalyze(exclude: string[]) {
    const d = await settle();
    if (!d) return;
    if (syncFailed.current) { notify("Chép file chưa xong, hãy thêm lại clip rồi thử lại"); return; }
    const g = ++gen.current;
    setAnalyzing(true); setErr(null); setPicked(null); setStepLabel("");
    try {
      const got = await engine.analyze(d, exclude, (e) => { if (g === gen.current && e.type === "step") setStepLabel(e.label); },
        (j) => { job.current = j; });
      if (g !== gen.current) return; // the media changed while this ran: these cards describe the old media
      shown.current = [...shown.current, ...got.map((c) => c.title)];
      setCards(got);
    } catch (e) {
      if (g === gen.current) setErr(toEngineError(e));
    } finally {
      if (g === gen.current) { job.current = null; setAnalyzing(false); }
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
        setMedia({ clips: d.clips, images: d.images }); setAsset("logo", d.logo); setAsset("music", d.music);
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

  /** Serialize a project sync behind the earlier ones; `pending` drives the "copying" state of the UI. */
  function enqueue(task: () => Promise<void>) {
    setPending((n) => n + 1);
    queue.current = queue.current.then(task).finally(() => setPending((n) => n - 1));
  }

  /** Replace each sent source path by the project's own copy in the CURRENT state (match by the sent path). */
  function adoptCopies(sent: Media, got: { clips: string[]; images: string[] }) {
    const local = new Map<string, string>();
    sent.clips.forEach((p, i) => { if (got.clips[i]) local.set(p, got.clips[i]); });
    sent.images.forEach((p, i) => { if (got.images[i]) local.set(p, got.images[i]); });
    local.forEach((v, k) => srcToInput.current.set(k, v));
    const cur = mediaRef.current;
    setMedia({ clips: cur.clips.map((p) => local.get(p) ?? p), images: cur.images.map((p) => local.get(p) ?? p) });
  }

  /** Apply a media change: update the UI now, then sync to the project (serialized, latest state wins). */
  function changeMedia(next: Media) {
    setMedia(next);
    gen.current++; // drops the result of any analyze that is still running on the old media
    void job.current?.cancel(); job.current = null; setAnalyzing(false);
    setCards([]); setPicked(null); setErr(null); shown.current = [];
    enqueue(async () => {
      const sent = mediaRef.current;
      try {
        let d = dirRef.current;
        let detail;
        if (!d) {
          if (sent.clips.length === 0) return; // images wait for the first clip
          const sentAssets = { logo: logoRef.current, music: musicRef.current };
          const p = await api.createProject(niche, sent.clips, sent.images, sentAssets.logo, sentAssets.music);
          // Assets picked while the project was being created: decide now, before any await, so none is sent twice.
          const late = (["logo", "music"] as const).filter((k) => {
            const cur = k === "logo" ? logoRef.current : musicRef.current;
            return cur && cur !== sentAssets[k];
          });
          d = p.dir; dirRef.current = d; setDir(d);
          for (const k of late) await api.setProjectAsset(d, k, (k === "logo" ? logoRef : musicRef).current);
          await refreshProjects();
          detail = await api.getProject(d);
        } else {
          detail = await api.setProjectMedia(d, sent.clips, sent.images);
        }
        syncFailed.current = false;
        adoptCopies(sent, detail);
      } catch (e) {
        syncFailed.current = true;
        if (!dirRef.current) setMedia({ clips: [], images: mediaRef.current.images });
        setErr(toEngineError(e));
      }
    });
  }

  function addMedia(c: Classified) {
    const cur = mediaRef.current;
    const has = (list: string[], p: string) => list.includes(p) || list.includes(srcToInput.current.get(p) ?? "\0");
    const clips = [...cur.clips, ...c.clips.filter((p, i, all) => !has(cur.clips, p) && all.indexOf(p) === i)];
    const images = [...cur.images, ...c.images.filter((p, i, all) => !has(cur.images, p) && all.indexOf(p) === i)];
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

  function onAsset(kind: "logo" | "music", path: string) {
    setAsset(kind, path);
    // No project yet: createProject (or the check right after it) picks the latest value up from the ref.
    if (!dirRef.current) return;
    enqueue(async () => {
      try { await api.setProjectAsset(dirRef.current!, kind, path); } catch (e) { notify(toEngineError(e).message); }
    });
  }

  async function pick(i: number) {
    setPicked(i);
    setPrompt(cards[i].prompt);
    if (dir) { try { await api.updateProject(dir, { script_card: cards[i] }); } catch { /* non-fatal */ } }
  }

  const canBuild = !!dir && pending === 0 && !analyzing && (prompt.trim() !== "" || picked !== null);

  async function build() {
    const dir = await settle();
    if (!dir) return;
    if (syncFailed.current) { notify("Chép file chưa xong, hãy thêm lại clip rồi thử lại"); return; }
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
            {cards.length > 0 && !analyzing && dir && pending === 0 && (
              <button className="linkbtn" onClick={() => void runAnalyze(shown.current)}>↻ Gợi ý khác</button>
            )}
          </div>
          {analyzing && (
            <div className="sc-empty"><span className="spin" /> AI đang xem clip…{stepLabel && <div className="hint">{stepLabel}</div>}</div>
          )}
          {!analyzing && cards.length === 0 && (
            <div className="sc-empty">
              <button className="btn" disabled={!dir || pending > 0} onClick={() => void runAnalyze([])}>✨ AI gợi ý kịch bản</button>
              {!dir && <div className="hint">Thêm clip để AI gợi ý</div>}
              {dir && pending > 0 && <div className="hint">Đang chép file…</div>}
            </div>
          )}
          {err && <div style={{ marginBottom: 8 }}><ErrorPanel compact error={err} onSettings={() => go({ name: "settings" })}
            onSetup={() => go({ name: "onboarding" })} onRetry={dir ? () => void runAnalyze(shown.current) : undefined} /></div>}
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
            <span className="hint">{!dir ? "Thêm clip để bắt đầu" : pending > 0 ? "Đang chép file…" : ""}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
