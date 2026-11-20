import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { Card, EngineError, EngineEvent } from "./types";

export type EngineResult = { code: number | null; last: EngineEvent | null; error: EngineError | null };
export type EngineJob = { result: Promise<EngineResult>; cancel(): Promise<void> };

type EventPayload = { job: string; event: EngineEvent };
type ExitPayload = { job: string; code: number | null };

export function runEngine(args: string[], onEvent?: (e: EngineEvent) => void): EngineJob {
  let jobId: string | null = null;
  let last: EngineEvent | null = null;
  let error: EngineError | null = null;
  let exit: ExitPayload | null = null;
  let finish!: (r: EngineResult) => void;
  let fail!: (e: unknown) => void;
  const buffered: EventPayload[] = [];
  const unlisteners: UnlistenFn[] = [];
  let cancelled = false;
  const result = new Promise<EngineResult>((res, rej) => { finish = res; fail = rej; });

  const cleanup = () => { unlisteners.splice(0).forEach((u) => u()); };
  const handle = (p: EventPayload) => {
    last = p.event;
    if (p.event.type === "error") error = p.event;
    onEvent?.(p.event);
  };
  const maybeFinish = () => {
    if (jobId !== null && exit && exit.job === jobId) {
      cleanup();
      finish({ code: exit.code, last, error });
    }
  };

  (async () => {
    try {
      unlisteners.push(await listen<EventPayload>("engine-event", (e) => {
        if (jobId === null) buffered.push(e.payload);
        else if (e.payload.job === jobId) handle(e.payload);
      }));
      unlisteners.push(await listen<ExitPayload>("engine-exit", (e) => {
        if (jobId === null) { exit = e.payload; return; }
        if (e.payload.job === jobId) { exit = e.payload; maybeFinish(); }
      }));
      const id = await invoke<string>("engine_run", { args });
      jobId = id;
      for (const p of buffered.splice(0)) if (p.job === id) handle(p);
      if (exit && (exit as ExitPayload).job !== id) exit = null;
      maybeFinish();
      if (cancelled) await invoke("engine_cancel", { job: id });
    } catch (e) {
      cleanup();
      fail(e);
    }
  })();

  return {
    result,
    async cancel() {
      cancelled = true;
      if (jobId !== null) await invoke("engine_cancel", { job: jobId });
    },
  };
}

function failure(r: EngineResult, fallback: string): Error {
  return new Error(r.error?.message || fallback);
}

export async function setupCli(): Promise<string> {
  const r = await runEngine(["setup"]).result;
  if (r.error) throw failure(r, "Không tải được Claude");
  if (r.last?.type !== "setup") throw failure(r, "Không tải được Claude");
  return r.last.claude_cli;
}

export async function setupModel(onProgress?: (p: number) => void): Promise<void> {
  const r = await runEngine(["setup-model"], (e) => {
    if (e.type === "step") onProgress?.(e.progress);
  }).result;
  if (r.error || r.last?.type !== "model") throw failure(r, "Không tải được model giọng nói");
}

export async function authCheck(): Promise<string> {
  const r = await runEngine(["auth-check"]).result;
  if (r.error) throw r.error;
  if (r.last?.type !== "auth") throw new Error("Chưa đăng nhập Claude");
  return r.last.source;
}

export async function analyze(dir: string, exclude: string[], onEvent?: (e: EngineEvent) => void): Promise<Card[]> {
  const args = ["analyze", "--project", dir];
  for (const t of exclude) args.push("--exclude", t);
  const r = await runEngine(args, onEvent).result;
  if (r.error) throw r.error;
  if (r.last?.type !== "cards") throw new Error("AI không gợi ý được kịch bản");
  return r.last.cards;
}
