import { createContext, useCallback, useContext, useEffect, useReducer, type Dispatch, type ReactNode } from "react";
import * as api from "../lib/api";
import type { ProjectSummary, Settings } from "../lib/types";

export type Route =
  | { name: "onboarding" }
  | { name: "niche" }
  | { name: "new"; niche: string }
  | { name: "project"; dir: string }
  | { name: "settings" };

export type PendingEdit = { dir: string; prompt: string; feedback?: string };

export type State = {
  route: Route;
  settings: Settings | null;
  projects: ProjectSummary[];
  auth: string | null;
  cliPath: string | null;
  pendingEdit: PendingEdit | null;
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
  | { type: "toast"; toast: string | null }
  | { type: "ready" };

const initial: State = {
  route: { name: "niche" },
  settings: null,
  projects: [],
  auth: null,
  cliPath: null,
  pendingEdit: null,
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
};
const StoreCtx = createContext<Ctx | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial);

  const refreshProjects = useCallback(async () => {
    dispatch({ type: "projects", projects: await api.listProjects() });
  }, []);
  const go = useCallback((route: Route) => dispatch({ type: "route", route }), []);
  const notify = useCallback((msg: string) => dispatch({ type: "toast", toast: msg }), []);

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

  return <StoreCtx.Provider value={{ state, dispatch, refreshProjects, go, notify }}>{children}</StoreCtx.Provider>;
}

export function useStore(): Ctx {
  const c = useContext(StoreCtx);
  if (!c) throw new Error("useStore must be used inside StoreProvider");
  return c;
}
