import { useCallback, useEffect, useRef, useState } from "react";
import ErrorPanel from "../components/ErrorPanel";
import * as api from "../lib/api";
import { runEngine, type EngineJob } from "../lib/engine";
import { toEngineError, type AnyEngineError } from "../lib/errors";
import type { EngineEvent, ProjectDetail } from "../lib/types";
import { useStore, type PendingEdit } from "../state/store";
import Building, { type BuildState } from "./Building";
import Result from "./Result";

const EMPTY: BuildState = { progress: 0, label: "", items: [], preview: null };

export default function ProjectView({ dir }: { dir: string }) {
  const { state, dispatch, go, refreshProjects, notify } = useStore();
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [build, setBuild] = useState<BuildState | null>(null);
  const [error, setError] = useState<AnyEngineError | null>(null);
  const job = useRef<EngineJob | null>(null);
  const last = useRef<{ prompt: string; feedback?: string } | null>(null);
  const handled = useRef<PendingEdit | null>(null);
  const detailRef = useRef<ProjectDetail | null>(null);
  detailRef.current = detail;

  const load = useCallback(async () => {
    try { setDetail(await api.getProject(dir)); } catch (e) { setError(toEngineError(e)); }
  }, [dir]);

  const start = useCallback(async (prompt: string, feedback?: string) => {
    last.current = { prompt, feedback };
    setError(null);
    setBuild(EMPTY);
    const onEvent = (e: EngineEvent) => {
      setBuild((b) => {
        const cur = b ?? EMPTY;
        if (e.type === "step") return { ...cur, progress: e.progress, label: e.label };
        if (e.type === "agent") return { ...cur, items: [...cur.items, { text: e.text, tool: e.tool }] };
        if (e.type === "preview") return { ...cur, preview: { path: e.path, round: e.round } };
        return cur;
      });
    };
    const args = ["edit", "--project", dir, "--prompt", prompt, ...(feedback ? ["--feedback", feedback] : [])];
    try {
      const j = runEngine(args, onEvent);
      job.current = j;
      const r = await j.result;
      if (r.last?.type === "done") {
        await load();
        await refreshProjects();
      } else if (r.error) {
        setError(r.error);
      } else {
        notify("Đã hủy");
      }
    } catch (e) {
      setError(toEngineError(e));
    } finally {
      job.current = null;
      setBuild(null);
    }
  }, [dir, load, refreshProjects, notify]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    const p = state.pendingEdit;
    if (!p || p.dir !== dir || handled.current === p) return;
    handled.current = p;
    dispatch({ type: "pendingEdit", pendingEdit: null });
    void start(p.prompt, p.feedback);
  }, [state.pendingEdit, dir, dispatch, start]);

  const retry = () => {
    const l = last.current ?? (detailRef.current ? { prompt: detailRef.current.prompt } : null);
    if (l) void start(l.prompt, l.feedback);
  };

  if (build) return <div className="view on"><Building build={build} onCancel={() => void job.current?.cancel()} /></div>;

  const hasRuns = !!detail && detail.runs.length > 0;
  return (
    <div className="view on">
      {error && (
        <div style={{ marginBottom: 16 }}>
          <ErrorPanel error={error} onRetry={retry} onSettings={() => go({ name: "settings" })} onSetup={() => go({ name: "onboarding" })} />
        </div>
      )}
      {detail && hasRuns && (
        <Result detail={detail} onRedo={(fb) => void start(detail.prompt, fb)} />
      )}
      {detail && !hasRuns && !error && (
        <div className="lock">
          <div className="big">🎬</div>
          <h2>{detail.title}</h2>
          <p>Video này chưa được dựng.</p>
          <button className="btn primary" onClick={() => go({ name: "new", niche: detail.niche })}>Dựng video</button>
        </div>
      )}
    </div>
  );
}
