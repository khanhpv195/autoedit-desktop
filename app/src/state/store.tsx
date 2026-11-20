import { createContext, useCallback, useContext, useEffect, useReducer, useRef, type Dispatch, type ReactNode } from "react";
import * as api from "../lib/api";
import { routineSync, runEngine, socialPublish, type EngineJob, type PublishArgs } from "../lib/engine";
import { toEngineError, type AnyEngineError } from "../lib/errors";
import type { EngineEvent, Post, ProjectSummary, Settings, SocialAccount } from "../lib/types";
import type { BuildState } from "../screens/Building";

export type Route =
  | { name: "onboarding" }
  | { name: "niche" }
  | { name: "new"; niche: string; dir?: string }
  | { name: "project"; dir: string }
  | { name: "settings"; tab?: "gen" | "conn" | "agent" }
  | { name: "schedule" };

/** An in-flight publish, keyed by `<project dir>#<run>`. */
export type PublishState = { label: string; progress: number };
export const publishKey = (dir: string, run: number) => `${dir}#${run}`;
type SyncResult = { created: Post[]; skipped: string | null };

export type PendingEdit = { dir: string; prompt: string; feedback?: string };

export type LastEdit = { prompt: string; feedback?: string };

const EMPTY_BUILD: BuildState = { progress: 0, label: "", items: [], preview: null };

export type State = {
  route: Route;
  settings: Settings | null;
  projects: ProjectSummary[];
  auth: string | null;
  /** A bundle.social key is stored (never the key itself). */
  hasSocialKey: boolean;
  /** Last bundle.social account read, cached for the post card and settings. */
  social: SocialAccount | null;
  cliPath: string | null;
  pendingEdit: PendingEdit | null;
  /** Running edit jobs, keyed by project dir. Survives navigating between screens. */
  builds: Record<string, BuildState>;
  buildErrors: Record<string, AnyEngineError>;
  lastEdits: Record<string, LastEdit>;
  /** Running publishes, keyed by dir#run. Survives leaving the Result screen. */
  publishes: Record<string, PublishState>;
  publishDone: Record<string, Post>;
  publishErrors: Record<string, AnyEngineError>;
  /** A routine sync (startup or "Chạy ngay") is running. */
  routineRunning: boolean;
  toast: string | null;
  ready: boolean;
};

export type Action =
  | { type: "route"; route: Route }
  | { type: "settings"; settings: Settings }
  | { type: "projects"; projects: ProjectSummary[] }
  | { type: "auth"; auth: string | null }
  | { type: "socialKey"; has: boolean }
  | { type: "social"; social: SocialAccount | null }
  | { type: "cliPath"; cliPath: string | null }
  | { type: "pendingEdit"; pendingEdit: PendingEdit | null }
  | { type: "buildStart"; dir: string; last: LastEdit }
  | { type: "buildEvent"; dir: string; event: EngineEvent }
  | { type: "buildEnd"; dir: string; error?: AnyEngineError }
  | { type: "publishStart"; key: string }
  | { type: "publishStep"; key: string; label: string; progress: number }
  | { type: "publishEnd"; key: string; post?: Post; error?: AnyEngineError }
  | { type: "publishClear"; key: string }
  | { type: "routineRunning"; running: boolean }
  | { type: "toast"; toast: string | null }
  | { type: "ready" };

const initial: State = {
  route: { name: "niche" },
  settings: null,
  projects: [],
  auth: null,
  hasSocialKey: false,
  social: null,
  cliPath: null,
  pendingEdit: null,
  builds: {},
  buildErrors: {},
  lastEdits: {},
  publishes: {},
  publishDone: {},
  publishErrors: {},
  routineRunning: false,
  toast: null,
  ready: false,
};

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "route": return { ...s, route: a.route };
    case "settings": return { ...s, settings: a.settings };
    case "projects": return { ...s, projects: a.projects };
    case "auth": return { ...s, auth: a.auth };
    case "socialKey": return { ...s, hasSocialKey: a.has, social: a.has ? s.social : null };
    case "social": return { ...s, social: a.social };
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
    case "publishStart": {
      const { [a.key]: _d, ...done } = s.publishDone;
      const { [a.key]: _e, ...errors } = s.publishErrors;
      return { ...s, publishes: { ...s.publishes, [a.key]: { label: "", progress: 0 } }, publishDone: done, publishErrors: errors };
    }
    case "publishStep":
      return s.publishes[a.key] ? { ...s, publishes: { ...s.publishes, [a.key]: { label: a.label, progress: a.progress } } } : s;
    case "publishEnd": {
      const { [a.key]: _p, ...publishes } = s.publishes;
      return {
        ...s, publishes,
        publishDone: a.post ? { ...s.publishDone, [a.key]: a.post } : s.publishDone,
        publishErrors: a.error ? { ...s.publishErrors, [a.key]: a.error } : s.publishErrors,
      };
    }
    case "publishClear": {
      const { [a.key]: _d, ...done } = s.publishDone;
      const { [a.key]: _e, ...errors } = s.publishErrors;
      return { ...s, publishDone: done, publishErrors: errors };
    }
    case "routineRunning": return { ...s, routineRunning: a.running };
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
  /** Publish a run. Ignored while one is already running for that dir#run. */
  startPublish(a: PublishArgs): void;
  cancelPublish(key: string): void;
  /** Run routine-sync. A second call while one is running returns the first one's result. */
  syncRoutine(team: string): Promise<SyncResult>;
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

  const pubJobs = useRef(new Map<string, EngineJob>());
  const pubCancelled = useRef(new Set<string>());
  const startPublish = useCallback((a: PublishArgs) => {
    const key = publishKey(a.dir, a.run);
    if (pubJobs.current.has(key)) return;
    pubCancelled.current.delete(key);
    dispatch({ type: "publishStart", key });
    void (async () => {
      let post: Post | undefined;
      let error: AnyEngineError | undefined;
      try {
        post = await socialPublish(
          a,
          (label, progress) => dispatch({ type: "publishStep", key, label, progress }),
          (job) => { pubJobs.current.set(key, job); },
        );
        await refreshProjects();
      } catch (e) {
        if (pubCancelled.current.has(key)) notify("Đã hủy đăng");
        else error = toEngineError(e);
      } finally {
        pubJobs.current.delete(key);
        pubCancelled.current.delete(key);
        dispatch({ type: "publishEnd", key, post, error });
      }
    })();
  }, [refreshProjects, notify]);
  const cancelPublish = useCallback((key: string) => {
    const job = pubJobs.current.get(key);
    if (!job) return;
    pubCancelled.current.add(key);
    void job.cancel();
  }, []);

  const syncing = useRef<Promise<SyncResult> | null>(null);
  const syncRoutine = useCallback((team: string): Promise<SyncResult> => {
    if (syncing.current) return syncing.current;
    dispatch({ type: "routineRunning", running: true });
    const p = routineSync(team).finally(() => {
      syncing.current = null;
      dispatch({ type: "routineRunning", running: false });
    });
    syncing.current = p;
    return p;
  }, []);

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
          let hasKey = false;
          try { hasKey = !!(await api.socialKeyStatus())?.hasKey; } catch { /* no key info: treat as none */ }
          if (!alive) return;
          dispatch({ type: "socialKey", has: hasKey });
          const team = settings.socialTeamId;
          if (hasKey && team && (settings.routines ?? []).some((r) => r.enabled)) {
            // Once per launch: create the next 7 days of routine posts. Failure is only a soft toast.
            syncRoutine(team)
              .then((r) => {
                if (!alive) return;
                if (r.skipped) notify(r.skipped);
                else if (r.created.length) notify(`Routine đã tạo ${r.created.length} bài`);
              })
              .catch(() => { if (alive) notify("Chưa chạy được routine, thử lại ở tab Lịch đăng"); });
          }
        }
      } catch {
        // keep defaults; the screens surface their own errors
      } finally {
        if (alive) dispatch({ type: "ready" });
      }
    })();
    return () => { alive = false; };
  }, [notify, syncRoutine]);

  useEffect(() => {
    if (!state.toast) return;
    const t = setTimeout(() => dispatch({ type: "toast", toast: null }), 3000);
    return () => clearTimeout(t);
  }, [state.toast]);

  return <StoreCtx.Provider value={{ state, dispatch, refreshProjects, go, notify, startBuild, cancelBuild, startPublish, cancelPublish, syncRoutine }}>{children}</StoreCtx.Provider>;
}

export function useStore(): Ctx {
  const c = useContext(StoreCtx);
  if (!c) throw new Error("useStore must be used inside StoreProvider");
  return c;
}
