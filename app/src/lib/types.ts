export type Routine = { id: string; time: string; channels: string[]; enabled: boolean };
export type Settings = {
  model: string; projectsRoot: string; lastNiche: string | null; onboarded: boolean;
  socialTeamId?: string | null; routines?: Routine[];
  voiceId?: string | null; voiceName?: string | null;
  defaultLogo?: string | null; defaultCta?: string;
};
export type ElevenStatus = { hasKey: boolean; remaining?: number };
export type Voice = { id: string; name: string; labels: Record<string, string>; previewUrl: string | null };
export type ProjectStatus = "new" | "done" | "needs_review";
export type ProjectSummary = {
  dir: string;
  title: string;
  niche: string;
  created: string;
  status: ProjectStatus;
  runCount: number;
  /** Posts still waiting on bundle.social: they post anyway after a delete. */
  scheduledPosts?: number;
  /** Poster frame of the last run (absolute path), if one exists. */
  thumb?: string | null;
};
export type Card = { title: string; hook: string; outline: string[] | string; prompt: string };
export type Run = {
  n: number;
  final: string;
  prompt: string;
  feedback: string | null;
  summary: string[];
  needsReview: boolean;
  fallback: boolean;
  /** Id of the video mẫu saved from this run, if any. */
  reference?: string | null;
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
  ctaText?: string;
  voiceover?: ProjectVoiceover | null;
  productInfo?: string;
};
export type ProjectVoiceover = { enabled: boolean; voiceId: string; voiceName: string };
export type ProjectPost = { id: string; run: number; postDate: string; channels: string[]; status: string };
export type ProjectPatch = {
  niche?: string; prompt?: string; script_card?: Card | null; target_seconds?: [number, number] | null;
};
/** The edit plan the chat agent agreed with the customer. */
export type ChatPlan = {
  summary: string[]; prompt: string; target_seconds: [number, number];
  length_source: "customer" | "ai"; length_reason: string; hook: string; cta: string;
};
export type ChatMessage =
  | { role: "user"; text: string; ts: number }
  | { role: "assistant"; text: string; suggestions: string[]; plan: ChatPlan | null; ts: number };
export type AuthSource = "app-token" | "claude-code" | "api-key" | null;
export type FeedItem = { text: string; tool: string | null };

export type EngineEvent =
  | { type: "step"; label: string; progress: number }
  | { type: "agent"; text: string; tool: string | null }
  | { type: "preview"; path: string; round: number }
  | { type: "done"; final: string; summary: string[]; usage: { turns: number; fallback: boolean }; needs_review: boolean }
  | { type: "thumb"; dir: string }
  | { type: "thumbs_done"; made: number }
  | { type: "error"; code: string; message: string; retry_at: string | null }
  | { type: "cards"; cards: Card[] }
  | { type: "chat"; message: Extract<ChatMessage, { role: "assistant" }> }
  | { type: "auth"; source: string }
  | { type: "setup"; claude_cli: string }
  | { type: "model"; path: string }
  | { type: "social_account"; organization: { name: string }; usage: SocialUsage; teams: SocialTeam[] }
  | { type: "social_portal"; url: string }
  | { type: "caption"; text: string }
  | { type: "social_post"; post: Post }
  | { type: "social_posts"; posts: Post[] }
  | { type: "routine_sync"; created: Post[]; skipped: string | null }
  | { type: "mcp_tools"; name: string; tools: McpTool[] }
  | { type: "reference"; reference: Reference }
  | { type: "references"; references: Reference[] };
/** A video mẫu the customer saved: the AI copies its structure in later edits. */
export type Reference = { id: string; name: string; niche: string; project: string; run: number; saved_at: number };
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
