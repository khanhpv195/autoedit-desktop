export type Settings = { model: string; projectsRoot: string; lastNiche: string | null; onboarded: boolean };
export type ProjectStatus = "new" | "done" | "needs_review";
export type ProjectSummary = {
  dir: string;
  title: string;
  niche: string;
  created: string;
  status: ProjectStatus;
  runCount: number;
};
export type Card = { title: string; hook: string; outline: string; prompt: string };
export type Run = {
  n: number;
  final: string;
  prompt: string;
  feedback: string | null;
  summary: string[];
  needsReview: boolean;
  fallback: boolean;
};
export type ProjectDetail = ProjectSummary & {
  clip: string;
  logo: string | null;
  music: string | null;
  prompt: string;
  scriptCard: Card | null;
  runs: Run[];
};
export type ProjectPatch = { niche?: string; prompt?: string; script_card?: Card };
export type AuthSource = "app-token" | "claude-code" | "api-key" | null;
export type FeedItem = { text: string; tool: string | null };

export type EngineEvent =
  | { type: "step"; label: string; progress: number }
  | { type: "agent"; text: string; tool: string | null }
  | { type: "preview"; path: string; round: number }
  | { type: "done"; final: string; summary: string[]; usage: { turns: number; fallback: boolean }; needs_review: boolean }
  | { type: "error"; code: string; message: string; retry_at: string | null }
  | { type: "cards"; cards: Card[] }
  | { type: "auth"; source: string }
  | { type: "setup"; claude_cli: string }
  | { type: "model"; path: string };
export type EngineError = Extract<EngineEvent, { type: "error" }>;
export type LoginOutput = { line: string; url: string | null };
export type LoginDone = { ok: boolean; error: string | null };
