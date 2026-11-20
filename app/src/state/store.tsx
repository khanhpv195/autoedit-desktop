import { createContext, useCallback, useContext, useEffect, useReducer, useRef, type Dispatch, type ReactNode } from "react";
import * as api from "../lib/api";
import { runEngine, type EngineJob } from "../lib/engine";
import { toEngineError, type AnyEngineError } from "../lib/errors";
import type { EngineEvent, ProjectSummary, Settings } from "../lib/types";
import type { BuildState } from "../screens/Building";

export type Route =
  | { name: "onboarding" }
  | { name: "niche" }
  | { name: "new"; niche: string; dir?: string }
  | { name: "project"; dir: string }
  | { name: "settings" };

export type PendingEdit = { dir: string; prompt: string; feedback?: string };

export type LastEdit = { prompt: string; feedback?: string };

const EMPTY_BUILD: BuildState = { progress: 0, label: "", items: [], preview: null };

export type State = {
  route: Route;
  settings: Settings | null;
  projects: ProjectSummary[];
  auth: string | null;
  cliPath: string | null;
  pendingEdit: PendingEdit | null;
  /** Running edit jobs, keyed by project dir. Survives navigating between screens. */
  builds: Record<string, BuildState>;
  buildErrors: Record<string, AnyEngineError>;
  lastEdits: Record<string, LastEdit>;
  toast: string | null;
  ready: boolean;
};

export type Action =
  | { type: "route"; route: Route }
  | { type: "settings"; settings: Settings }
  | { type: "projects"; projects: ProjectSummary[] }
  | { type: "auth"; auth: string | null }
  | { type: "cliPath"; cliPath: string | null }
  | { type: "pendingEdit"; pendingEdit: PendingEdit | null }
  | { type: "buildStart"; dir: string; last: LastEdit }
  | { type: "buildEvent"; dir: string; event: EngineEvent }
  | { type: "buildEnd"; dir: string; error?: AnyEngineError }
  | { type: "toast"; toast: string | null }
  | { type: "ready" };

const initial: State = {
  route: { name: "niche" },
  settings: null,
  projects: [],
  auth: null,
  cliPath: null,
  pendingEdit: null,
  builds: {},
  buildErrors: {},
  lastEdits: {},
  toast: null,
  ready: false,
};

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "route": return { ...s, route: a.route };
    case "settings": return { ...s, settings: a.settings };
    case "projects": return { ...s, projects: a.projects };
    case "auth": return { ...s, auth: a.auth };
    case "cliPath": return { ...s, cliPath: a.cliPath };
    case "pendingEdit": return { ...s, pendingEdit: a.pendingEdit };
    case "buildStart": {
      const { [a.dir]: _gone, ...errors } = s.buildErrors;
      return { ...s, builds: { ...s.builds, [a.dir]: EMPTY_BUILD }, buildErrors: errors, lastEdits: { ...s.lastEdits, [a.dir]: a.last } };
    }
    case "buildEvent": {
      const cur = s.builds[a.dir];
      if (!cur) return s;
      const e = a.event;
      let next = cur;
      if (e.type === "step") next = { ...cur, progress: e.progress, label: e.label };
      else if (e.type === "agent") next = { ...cur, items: [...cur.items, { text: e.text, tool: e.tool }] };
      else if (e.type === "preview") next = { ...cur, preview: { path: e.path, round: e.round } };
      return next === cur ? s : { ...s, builds: { ...s.builds, [a.dir]: next } };
    }
    case "buildEnd": {
      const { [a.dir]: _done, ...builds } = s.builds;
      const errors = a.error ? { ...s.buildErrors, [a.dir]: a.error } : s.buildErrors;
      return { ...s, builds, buildErrors: errors };
    }
    case "toast": return { ...s, toast: a.toast };
    case "ready": return { ...s, ready: true };
  }
}

type Ctx = {
  state: State;
  dispatch: Dispatch<Action>;
  refreshProjects(): Promise<void>;
  go(route: Route): void;
  notify(msg: string): void;
  /** Start an edit job for a project. Ignored while one is already running for that dir. */
  startBuild(dir: string, prompt: string, feedback?: string): void;
  cancelBuild(dir: string): void;
};
const StoreCtx = createContext<Ctx | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial);

  const refreshProjects = useCallback(async () => {
    dispatch({ type: "projects", projects: await api.listProjects() });
  }, []);
  const go = useCallback((route: Route) => dispatch({ type: "route", route }), []);
  const notify = useCallback((msg: string) => dispatch({ type: "toast", toast: msg }), []);

  const jobs = useRef(new Map<string, EngineJob>());
  const startBuild = useCallback((dir: string, prompt: string, feedback?: string) => {
    if (jobs.current.has(dir)) return;
    dispatch({ type: "buildStart", dir, last: { prompt, feedback } });
    const args = ["edit", "--project", dir, "--prompt", prompt, ...(feedback ? ["--feedback", feedback] : [])];
    void (async () => {
      let error: AnyEngineError | undefined;
      try {
        const job = runEngine(args, (event) => dispatch({ type: "buildEvent", dir, event }));
        jobs.current.set(dir, job);
        const r = await job.result;
        if (r.last?.type === "done") await refreshProjects();
        else if (r.error) error = r.error;
        else notify("Đã hủy");
      } catch (e) {
        error = toEngineError(e);
      } finally {
        jobs.current.delete(dir);
        dispatch({ type: "buildEnd", dir, error });
      }
    })();
  }, [refreshProjects, notify]);
  const cancelBuild = useCallback((dir: string) => { void jobs.current.get(dir)?.cancel(); }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const settings = await api.getSettings();
        if (!alive) return;
        dispatch({ type: "settings", settings });
        if (!settings.onboarded) {
          dispatch({ type: "route", route: { name: "onboarding" } });
        } else {
          const projects = await api.listProjects();
          if (!alive) return;
          dispatch({ type: "projects", projects });
          dispatch({ type: "route", route: { name: "niche" } });
        }
      } catch {
        // keep defaults; the screens surface their own errors
      } finally {
        if (alive) dispatch({ type: "ready" });
      }
    })();
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!state.toast) return;
    const t = setTimeout(() => dispatch({ type: "toast", toast: null }), 3000);
    return () => clearTimeout(t);
  }, [state.toast]);

  return <StoreCtx.Provider value={{ state, dispatch, refreshProjects, go, notify, startBuild, cancelBuild }}>{children}</StoreCtx.Provider>;
}

export function useStore(): Ctx {
  const c = useContext(StoreCtx);
  if (!c) throw new Error("useStore must be used inside StoreProvider");
  return c;
}
