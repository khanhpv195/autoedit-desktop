import { vi, test, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { StoreProvider, useStore } from "./store";

vi.mock("../lib/api");
vi.mock("../lib/engine");
const e = vi.mocked(engine);
const m = vi.mocked(api);

function Probe() {
  const { state } = useStore();
  return <div>route:{state.route.name} n:{state.projects.length}</div>;
}
const settings = { model: "claude-opus-5-5", projectsRoot: "/p", lastNiche: null };

beforeEach(() => vi.clearAllMocks());

test("not onboarded -> onboarding route", async () => {
  m.getSettings.mockResolvedValue({ ...settings, onboarded: false });
  render(<StoreProvider><Probe /></StoreProvider>);
  expect(await screen.findByText(/route:onboarding/)).toBeInTheDocument();
  expect(m.listProjects).not.toHaveBeenCalled();
});
test("onboarded -> loads projects, route niche", async () => {
  m.getSettings.mockResolvedValue({ ...settings, onboarded: true });
  m.listProjects.mockResolvedValue([{ dir: "/a", title: "A", niche: "chung", created: "2026-11-20", status: "new", runCount: 0 }]);
  render(<StoreProvider><Probe /></StoreProvider>);
  expect(await screen.findByText(/route:niche n:1/)).toBeInTheDocument();
  expect(m.listProjects).toHaveBeenCalled();
});

test("startup routine-sync runs once when there is a key, a team and an enabled routine", async () => {
  const routines = [{ id: "r", time: "19:30", channels: ["TIKTOK"], enabled: true }];
  m.getSettings.mockResolvedValue({ ...settings, onboarded: true, socialTeamId: "t1", routines });
  m.listProjects.mockResolvedValue([]);
  m.socialKeyStatus.mockResolvedValue({ hasKey: true });
  e.routineSync.mockResolvedValue({ created: [], skipped: null });
  render(<StoreProvider><Probe /></StoreProvider>);
  await screen.findByText(/route:niche/);
  await vi.waitFor(() => expect(e.routineSync).toHaveBeenCalledWith("t1"));
  expect(e.routineSync).toHaveBeenCalledTimes(1);
});

test("startup does not sync without key, team or an enabled routine", async () => {
  const on = [{ id: "r", time: "19:30", channels: ["TIKTOK"], enabled: true }];
  const off = [{ id: "r", time: "19:30", channels: ["TIKTOK"], enabled: false }];
  const cases: [any, boolean][] = [
    [{ socialTeamId: "t1", routines: on }, false],
    [{ socialTeamId: null, routines: on }, true],
    [{ socialTeamId: "t1", routines: off }, true],
  ];
  for (const [over, key] of cases) {
    vi.clearAllMocks();
    m.getSettings.mockResolvedValue({ ...settings, onboarded: true, ...over });
    m.listProjects.mockResolvedValue([]);
    m.socialKeyStatus.mockResolvedValue({ hasKey: key });
    const { unmount } = render(<StoreProvider><Probe /></StoreProvider>);
    await screen.findByText(/route:niche/);
    await new Promise((r) => setTimeout(r, 20));
    expect(e.routineSync).not.toHaveBeenCalled();
    unmount();
  }
});

test("syncRoutine shares one engine job: a second call while running gets the first result", async () => {
  m.getSettings.mockResolvedValue({ ...settings, onboarded: false });
  let finish!: (r: any) => void;
  e.routineSync.mockReturnValue(new Promise((res) => { finish = res; }));
  let ctx!: ReturnType<typeof useStore>;
  function Grab() { ctx = useStore(); return <div>running:{String(ctx.state.routineRunning)}</div>; }
  render(<StoreProvider><Grab /></StoreProvider>);
  const p1 = ctx.syncRoutine("t1");
  const p2 = ctx.syncRoutine("t1");
  expect(p2).toBe(p1);
  expect(e.routineSync).toHaveBeenCalledTimes(1);
  expect(await screen.findByText("running:true")).toBeInTheDocument();
  const result = { created: [], skipped: "Routine đang chạy" };
  finish(result);
  expect(await p1).toBe(result);
  expect(await screen.findByText("running:false")).toBeInTheDocument();
  e.routineSync.mockResolvedValue({ created: [], skipped: null });
  await ctx.syncRoutine("t1");
  expect(e.routineSync).toHaveBeenCalledTimes(2);
});

test("startup sync shows a skipped message as a normal toast", async () => {
  const routines = [{ id: "r", time: "19:30", channels: ["TIKTOK"], enabled: true }];
  m.getSettings.mockResolvedValue({ ...settings, onboarded: true, socialTeamId: "t1", routines });
  m.listProjects.mockResolvedValue([]);
  m.socialKeyStatus.mockResolvedValue({ hasKey: true });
  e.routineSync.mockResolvedValue({ created: [], skipped: "Routine đang chạy" });
  function T() { const { state } = useStore(); return <div>toast:{state.toast}</div>; }
  render(<StoreProvider><T /></StoreProvider>);
  expect(await screen.findByText("toast:Routine đang chạy")).toBeInTheDocument();
});
