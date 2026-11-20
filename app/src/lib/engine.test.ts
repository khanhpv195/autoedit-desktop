import { vi, test, expect } from "vitest";
const handlers: Record<string, (e: { payload: any }) => void> = {};
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(async (name: string, cb: any) => { handlers[name] = cb; return () => delete handlers[name]; }),
}));
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async (cmd: string) => {
    if (cmd === "engine_run") {
      handlers["engine-event"]({ payload: { job: "j1", event: { type: "step", label: "a", progress: 0.5 } } });
      queueMicrotask(() => {
        handlers["engine-event"]({ payload: { job: "other", event: { type: "step", label: "x", progress: 0 } } });
        handlers["engine-event"]({ payload: { job: "j1", event: { type: "setup", claude_cli: "/c" } } });
        handlers["engine-exit"]({ payload: { job: "j1", code: 0 } });
      });
      return "j1";
    }
  }),
  convertFileSrc: (p: string) => "asset://" + p,
}));
import { runEngine, setupCli } from "./engine";

test("buffers early events, filters by job, resolves on exit", async () => {
  const seen: any[] = [];
  const r = await runEngine(["setup"], (e) => seen.push(e)).result;
  expect(seen.map((e) => e.type)).toEqual(["step", "setup"]);
  expect(r.code).toBe(0); expect(r.last?.type).toBe("setup");
});
test("setupCli returns the cli path", async () => {
  expect(await setupCli()).toBe("/c");
});
