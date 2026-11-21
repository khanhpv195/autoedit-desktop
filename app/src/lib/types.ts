export type Routine = { id: string; time: string; channels: string[]; enabled: boolean };
export type Settings = {
  model: string; projectsRoot: string; lastNiche: string | null; onboarded: boolean;
  socialTeamId?: string | null; routines?: Routine[];
};
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
  clips: string[];
  images: string[];
  logo: string | null;
  music: string | null;
  prompt: string;
  scriptCard: Card | null;
  runs: Run[];
  posts?: ProjectPost[];
};
export type ProjectPost = { id: string; run: number; postDate: string; channels: string[]; status: string };
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
  | { type: "model"; path: string }
  | { type: "social_account"; organization: { name: string }; usage: SocialUsage; teams: SocialTeam[] }
  | { type: "social_portal"; url: string }
  | { type: "caption"; text: string }
  | { type: "social_post"; post: Post }
  | { type: "social_posts"; posts: Post[] }
  | { type: "routine_sync"; created: Post[]; skipped: string | null }
  | { type: "mcp_tools"; name: string; tools: McpTool[] };
export type Quota = { used: number; limit: number; remaining: number };
export type SocialUsage = { posts: Quota; uploads: Quota };
export type SocialChannel = { type: string; name: string; avatar: string | null; username: string | null };
export type SocialTeam = { id: string; name: string; channels: SocialChannel[] };
export type SocialAccount = Extract<EngineEvent, { type: "social_account" }>;
export type Post = {
  id: string; title: string; status: string; postDate: string; channels: string[];
  error: string | null; project: string | null; run: number | null; permalinks: Record<string, string>;
};
export type McpTool = { name: string; description: string };
export type McpServer = {
  name: string; enabled: boolean; transport: "stdio" | "http";
  command?: string; args?: string[]; envKeys?: string[];
  url?: string; headerKeys?: string[];
};
export type EngineError = Extract<EngineEvent, { type: "error" }>;
export type LoginOutput = { line: string; url: string | null };
export type LoginDone = { ok: boolean; error: string | null };
