import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { Card, ChatMessage, EngineError, EngineEvent, McpTool, Post, Reference, SocialAccount } from "./types";

export type EngineResult = { code: number | null; last: EngineEvent | null; error: EngineError | null };
export type EngineJob = { result: Promise<EngineResult>; cancel(): Promise<void> };

type EventPayload = { job: string; event: EngineEvent };
type ExitPayload = { job: string; code: number | null };

export function runEngine(args: string[], onEvent?: (e: EngineEvent) => void): EngineJob {
  let jobId: string | null = null;
  let last: EngineEvent | null = null;
  let error: EngineError | null = null;
  const exits: ExitPayload[] = []; // exits that arrive before the job id is known (any job)
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
    const mine = jobId === null ? undefined : exits.find((x) => x.job === jobId);
    if (mine) {
      cleanup();
      finish({ code: mine.code, last, error });
    }
  };

  (async () => {
    try {
      unlisteners.push(await listen<EventPayload>("engine-event", (e) => {
        if (jobId === null) buffered.push(e.payload);
        else if (e.payload.job === jobId) handle(e.payload);
      }));
      unlisteners.push(await listen<ExitPayload>("engine-exit", (e) => {
        exits.push(e.payload);
        if (jobId !== null) maybeFinish();
      }));
      const id = await invoke<string>("engine_run", { args });
      jobId = id;
      for (const p of buffered.splice(0)) if (p.job === id) handle(p);
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

export async function setupCli(onProgress?: (p: number, label: string) => void): Promise<string> {
  const r = await runEngine(["setup"], (e) => {
    if (e.type === "step") onProgress?.(e.progress, e.label);
  }).result;
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

export async function analyze(
  dir: string, exclude: string[], onEvent?: (e: EngineEvent) => void, onJob?: (job: EngineJob) => void,
): Promise<Card[]> {
  const args = ["analyze", "--project", dir];
  for (const t of exclude) args.push("--exclude", t);
  const job = runEngine(args, onEvent);
  onJob?.(job);
  const r = await job.result;
  if (r.error) throw r.error;
  if (r.last?.type !== "cards") throw new Error("AI không gợi ý được kịch bản");
  return r.last.cards;
}

/** One chat turn (empty message = the opening turn). Resolves with the assistant's reply, already saved to chat.json. */
export async function chat(
  dir: string, message: string, onEvent?: (e: EngineEvent) => void, onJob?: (job: EngineJob) => void,
): Promise<Extract<ChatMessage, { role: "assistant" }>> {
  // --message=… keeps a text that starts with "-" from being read as a flag
  const job = runEngine(["chat", "--project", dir, `--message=${message}`], onEvent);
  onJob?.(job);
  const r = await job.result;
  if (r.error) throw r.error;
  if (r.last?.type !== "chat") throw new Error("AI không trả lời được, thử gửi lại");
  return r.last.message;
}

async function social<T extends EngineEvent["type"]>(
  args: string[], type: T, fallback: string, onEvent?: (e: EngineEvent) => void,
): Promise<Extract<EngineEvent, { type: T }>> {
  const r = await runEngine(args, onEvent).result;
  if (r.error) throw r.error;
  if (r.last?.type !== type) throw new Error(fallback);
  return r.last as Extract<EngineEvent, { type: T }>;
}

export const socialCheck = (): Promise<SocialAccount> =>
  social(["social", "check"], "social_account", "Không đọc được tài khoản bundle.social");

export async function socialPortal(team: string): Promise<string> {
  return (await social(["social", "portal", "--team", team], "social_portal", "Không mở được trang quản lý kênh")).url;
}

export async function socialCaption(dir: string, run: number): Promise<string> {
  return (await social(["social", "caption", "--project", dir, "--run", String(run)], "caption", "AI không viết được caption")).text;
}

export type PublishArgs = { dir: string; run: number; team: string; channels: string[]; caption: string; when: string };
export async function socialPublish(
  a: PublishArgs, onStep?: (label: string, progress: number) => void, onJob?: (job: EngineJob) => void,
): Promise<Post> {
  const args = ["social", "publish", "--project", a.dir, "--run", String(a.run), "--team", a.team];
  for (const c of a.channels) args.push("--channel", c);
  args.push(`--caption=${a.caption}`, "--when", a.when);
  const job = runEngine(args, (ev) => {
    if (ev.type === "step") onStep?.(ev.label, ev.progress);
  });
  onJob?.(job);
  const r = await job.result;
  if (r.error) throw r.error;
  if (r.last?.type !== "social_post") throw new Error("Đăng bài không có kết quả");
  return r.last.post;
}

export async function socialList(team: string, from: string, to: string): Promise<Post[]> {
  return (await social(["social", "list", "--team", team, "--from", from, "--to", to], "social_posts", "Không đọc được lịch đăng")).posts;
}

export async function socialRetry(post: string): Promise<Post> {
  return (await social(["social", "retry", "--post", post], "social_post", "Thử lại không có kết quả")).post;
}

export async function routineSync(team: string): Promise<{ created: Post[]; skipped: string | null }> {
  const e = await social(["social", "routine-sync", "--team", team], "routine_sync", "Routine không chạy được");
  return { created: e.created, skipped: e.skipped };
}

export async function mcpCheck(name: string): Promise<McpTool[]> {
  return (await social(["mcp-check", "--name", name], "mcp_tools", "Không kết nối được MCP")).tools;
}

/** "Lưu làm mẫu": save one run as a video mẫu the AI reads in later chats and edits. */
export async function saveReference(dir: string, run: number): Promise<Reference> {
  return (await social(["reference", "save", "--project", dir, "--run", String(run)], "reference", "Không lưu được video mẫu")).reference;
}

export async function listReferences(): Promise<Reference[]> {
  return (await social(["reference", "list"], "references", "Không đọc được video mẫu")).references;
}

/** Resolves with the references left. */
export async function deleteReference(id: string): Promise<Reference[]> {
  return (await social(["reference", "delete", "--id", id], "references", "Không bỏ được video mẫu")).references;
}
