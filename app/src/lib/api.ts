import { invoke, convertFileSrc } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import type {
  AuthSource, FeedItem, McpServer, LoginDone, LoginOutput, ProjectDetail, ProjectPatch, ProjectSummary, Settings,
} from "./types";

export const getSettings = () => invoke<Settings>("get_settings");
export const saveSettings = (settings: Settings) => invoke<null>("save_settings", { settings });
export const authStatus = () => invoke<{ source: AuthSource }>("auth_status");
export const loginStart = (cliPath: string) => invoke<null>("login_start", { cliPath });
export const loginInput = (text: string) => invoke<null>("login_input", { text });
export const loginCancel = () => invoke<null>("login_cancel");
export const licenseStatus = () => invoke<{ licensed: boolean; name: string | null }>("license_status");
export const licenseActivate = (key: string) => invoke<{ licensed: true; name: string }>("license_activate", { key });
export const onLicenseRevoked = async (cb: (reason: string) => void): Promise<() => void> =>
  listen<{ reason: string }>("license-revoked", (e) => cb(e.payload.reason));
export const killAllJobs = () => invoke<null>("kill_all_jobs");
export const logout = () => invoke<null>("logout");
export const setApiKey = (key: string) => invoke<null>("set_api_key", { key });
export const clearApiKey = () => invoke<null>("clear_api_key");
export const socialKeyStatus = () => invoke<{ hasKey: boolean }>("social_key_status");
export const setSocialKey = (key: string) => invoke<null>("set_social_key", { key });
export const clearSocialKey = () => invoke<null>("clear_social_key");
export const mcpList = () => invoke<McpServer[]>("mcp_list");
export const mcpSave = (server: McpServer, secrets: Record<string, string>) => invoke<null>("mcp_save", { server, secrets });
export const mcpDelete = (name: string) => invoke<null>("mcp_delete", { name });
export const createProject = (niche: string, clips: string[], images: string[], logo: string | null, music: string | null) =>
  invoke<ProjectSummary>("create_project", { niche, clips, images, logo, music });
export const listProjects = () => invoke<ProjectSummary[]>("list_projects");
export const getProject = (dir: string) => invoke<ProjectDetail>("get_project", { dir });
export const updateProject = (dir: string, patch: ProjectPatch) => invoke<null>("update_project", { dir, patch });
export const setProjectAsset = (dir: string, kind: "logo" | "music", path: string | null) =>
  invoke<ProjectDetail>("set_project_asset", { dir, kind, path });
export const setProjectMedia = (dir: string, clips: string[], images: string[]) =>
  invoke<ProjectDetail>("set_project_media", { dir, clips, images });
export const readRunFeed = (dir: string, n: number) => invoke<FeedItem[]>("read_run_feed", { dir, n });

export const onLoginOutput = async (cb: (o: LoginOutput) => void): Promise<() => void> =>
  listen<LoginOutput>("login-output", (e) => cb(e.payload));
export const onLoginDone = async (cb: (o: LoginDone) => void): Promise<() => void> =>
  listen<LoginDone>("login-done", (e) => cb(e.payload));

export const fileSrc = (path: string) => convertFileSrc(path);

const FILTERS = {
  clip: { name: "Video", extensions: ["mp4", "mov", "m4v"] },
  logo: { name: "Ảnh", extensions: ["png", "jpg", "jpeg"] },
  music: { name: "Nhạc", extensions: ["mp3", "m4a", "wav"] },
} as const;
export async function pickFile(kind: "clip" | "logo" | "music"): Promise<string | null> {
  const r = await open({ multiple: false, directory: false, filters: [{ ...FILTERS[kind], extensions: [...FILTERS[kind].extensions] }] });
  return typeof r === "string" ? r : null;
}
export async function pickMedia(): Promise<string[]> {
  const r = await open({
    multiple: true, directory: false,
    filters: [{ name: "Clip và ảnh", extensions: ["mp4", "mov", "m4v", "png", "jpg", "jpeg", "webp"] }],
  });
  return Array.isArray(r) ? r : typeof r === "string" ? [r] : [];
}
export async function pickFolder(): Promise<string | null> {
  const r = await open({ multiple: false, directory: true });
  return typeof r === "string" ? r : null;
}
export const revealInFolder = (path: string) => revealItemInDir(path);
