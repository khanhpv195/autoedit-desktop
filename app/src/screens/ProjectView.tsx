import { Clapperboard } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import EditableTitle from "../components/EditableTitle";
import ErrorPanel from "../components/ErrorPanel";
import * as api from "../lib/api";
import { toEngineError, type AnyEngineError } from "../lib/errors";
import type { ProjectDetail } from "../lib/types";
import { useStore, type PendingEdit } from "../state/store";
import Building from "./Building";
import Result from "./Result";

export default function ProjectView({ dir }: { dir: string }) {
  const { state, dispatch, go, startBuild, cancelBuild } = useStore();
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [loadError, setLoadError] = useState<AnyEngineError | null>(null);
  const [reloading, setReloading] = useState(false);
  const handled = useRef<PendingEdit | null>(null);
  const detailRef = useRef<ProjectDetail | null>(null);
  detailRef.current = detail;

  // Running jobs live in the store, so leaving this screen neither loses nor duplicates them.
  const build = state.builds[dir] ?? null;
  const error = loadError ?? state.buildErrors[dir] ?? null;

  const load = useCallback(async () => {
    try { setLoadError(null); setDetail(await api.getProject(dir)); } catch (e) { setLoadError(toEngineError(e)); }
  }, [dir]);

  useEffect(() => { void load(); }, [load]);

  // A job that ends while this view is open (or ended while it was closed) means new runs on disk.
  const wasBuilding = useRef(!!build);
  useEffect(() => {
    if (wasBuilding.current && !build) {
      setReloading(true);
      void load().finally(() => setReloading(false));
    }
    wasBuilding.current = !!build;
  }, [build, load]);

  useEffect(() => {
    const p = state.pendingEdit;
    if (!p || p.dir !== dir || handled.current === p) return;
    handled.current = p;
    dispatch({ type: "pendingEdit", pendingEdit: null });
    startBuild(dir, p.prompt, p.feedback);
  }, [state.pendingEdit, dir, dispatch, startBuild]);

  const retry = () => {
    const l = state.lastEdits[dir] ?? (detailRef.current ? { prompt: detailRef.current.prompt } : null);
    if (l) startBuild(dir, l.prompt, l.feedback);
  };

  if (build) return <div className="view on"><Building build={build} onCancel={() => cancelBuild(dir)} /></div>;

  const hasRuns = !!detail && detail.runs.length > 0;
  return (
    <div className="view on">
      {error && (
        <div style={{ marginBottom: 16 }}>
          <ErrorPanel error={error} onRetry={retry} onSettings={() => go({ name: "settings" })} onSetup={() => go({ name: "onboarding" })} />
        </div>
      )}
      {detail && hasRuns && (
        <Result detail={detail} onRedo={(fb) => startBuild(dir, detail.prompt, fb)} onPosted={() => void load()} onRenamed={() => void load()} />
      )}
      {detail && !hasRuns && !error && !reloading && (
        <div className="lock">
          <div className="lockic"><Clapperboard aria-hidden /></div>
          <EditableTitle as="h2" dir={dir} title={detail.title} onRenamed={() => void load()} />
          <p>Video này chưa được dựng.</p>
          <button className="btn primary" onClick={() => go({ name: "new", niche: detail.niche, dir })}>Dựng video</button>
        </div>
      )}
    </div>
  );
}
