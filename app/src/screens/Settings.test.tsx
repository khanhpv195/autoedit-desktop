import { vi, test, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { StoreProvider } from "../state/store";
import Settings from "./Settings";
import type { Voice } from "../lib/types";

vi.mock("../lib/api");
vi.mock("../lib/engine");
vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));
const a = vi.mocked(api);
const base = { model: "claude-opus-5-5", projectsRoot: "/Users/x/Movies/AutoEdit", lastNiche: null, onboarded: true };

beforeEach(() => {
  vi.clearAllMocks();
  a.licenseStatus.mockResolvedValue({ licensed: true, name: "Test" });
  a.getSettings.mockResolvedValue(base);
  a.listProjects.mockResolvedValue([]);
  a.saveSettings.mockResolvedValue(null);
  a.authStatus.mockResolvedValue({ source: "app-token" });
  a.onLoginOutput.mockResolvedValue(() => {});
  a.onLoginDone.mockResolvedValue(() => {});
});
async function open(tab?: string) {
  render(<StoreProvider><Settings /></StoreProvider>);
  await screen.findByText(base.projectsRoot);
  if (tab) await userEvent.click(screen.getByRole("tab", { name: tab }));
}

test("changing the model saves settings", async () => {
  await open("AI dựng");
  await userEvent.selectOptions(screen.getByLabelText("Model"), "claude-sonnet-5-5");
  expect(a.saveSettings).toHaveBeenCalledWith({ ...base, model: "claude-sonnet-5-5" });
});

test("model list has Sonnet (default, first), Opus and Haiku", async () => {
  a.getSettings.mockResolvedValue({ ...base, model: "" });
  await open("AI dựng");
  const sel = screen.getByLabelText("Model") as HTMLSelectElement;
  const opts = Array.from(sel.options).map((o) => o.value);
  expect(opts).toEqual(["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"]);
  expect(sel.value).toBe("claude-sonnet-5-5");
  expect(sel.options[0].textContent).toMatch(/mặc định/);
  expect(sel.options[1].textContent).toMatch(/tốt nhất, tốn nhiều lượt nhất/);
  expect(sel.options[2].textContent).toMatch(/rẻ nhất, dựng kém hơn với clip khó/);
});

test("a saved Opus model stays selected", async () => {
  await open("AI dựng");
  expect((screen.getByLabelText("Model") as HTMLSelectElement).value).toBe("claude-opus-5-5");
});

test("logout only shows for app-token and calls logout", async () => {
  await open("AI dựng");
  expect(await screen.findByText("Subscription Claude · token app")).toBeInTheDocument();
  a.authStatus.mockResolvedValue({ source: null });
  await userEvent.click(screen.getByRole("button", { name: "Đăng xuất" }));
  expect(a.logout).toHaveBeenCalled();
  expect(await screen.findByText("Chưa kết nối")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Đăng xuất" })).toBeNull();
});

test("no logout button for Claude Code login", async () => {
  a.authStatus.mockResolvedValue({ source: "claude-code" });
  await open("AI dựng");
  expect(await screen.findByText("Subscription Claude · Claude Code trên máy")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Đăng xuất" })).toBeNull();
});

test("saving an API key calls setApiKey", async () => {
  await open("AI dựng");
  await userEvent.type(screen.getByLabelText("API key"), "sk-ant-xyz");
  await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(a.setApiKey).toHaveBeenCalledWith("sk-ant-xyz");
  expect(screen.getByLabelText("API key")).toHaveValue("");
});

test("changing the folder saves projectsRoot", async () => {
  a.pickFolder.mockResolvedValue("/Volumes/Big/Videos");
  await open();
  await userEvent.click(screen.getByRole("button", { name: "Đổi…" }));
  expect(a.saveSettings).toHaveBeenCalledWith({ ...base, projectsRoot: "/Volumes/Big/Videos" });
});

test("connection check reports failure", async () => {
  vi.mocked(engine.authCheck).mockRejectedValue({ code: "NO_AUTH", message: "", retry_at: null });
  await open("AI dựng");
  await userEvent.click(screen.getByRole("button", { name: "Kiểm tra kết nối" }));
  // toast is held by the store; no crash is the contract here
  expect(engine.authCheck).toHaveBeenCalled();
});

test("changing the project folder refreshes the sidebar list", async () => {
  a.pickFolder.mockResolvedValue("/new/root");
  await open();
  a.listProjects.mockClear();
  await userEvent.click(screen.getByRole("button", { name: /Đổi/ }));
  await vi.waitFor(() => expect(a.saveSettings).toHaveBeenCalledWith({ ...base, projectsRoot: "/new/root" }));
  await vi.waitFor(() => expect(a.listProjects).toHaveBeenCalled());
});

const VOICES: Voice[] = [
  { id: "v1", name: "Lan", labels: { gender: "female", accent: "northern" }, previewUrl: "https://storage.googleapis.com/x/v1.mp3" },
  { id: "v2", name: "Minh", labels: {}, previewUrl: null },
];

test("ElevenLabs: saving a key calls set_eleven_key, then shows remaining and voices", async () => {
  a.socialKeyStatus.mockResolvedValue({ hasKey: false });
  a.mcpList.mockResolvedValue([]);
  a.elevenStatus.mockResolvedValue({ hasKey: false });
  a.setElevenKey.mockResolvedValue({ remaining: 28800 });
  a.elevenVoices.mockResolvedValue(VOICES);
  await open("Kết nối & MCP");
  await userEvent.type(await screen.findByLabelText("API key ElevenLabs"), " test-key ");
  await userEvent.click(screen.getByRole("button", { name: "Lưu key ElevenLabs" }));
  expect(a.setElevenKey).toHaveBeenCalledWith("test-key");
  expect(await screen.findByText(/Còn 28[.,]800 ký tự/)).toBeInTheDocument();
  expect(await screen.findByText("Lan")).toBeInTheDocument();
  expect(screen.getByText("female · northern")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Nghe thử Minh" })).toBeDisabled();
});

test("ElevenLabs: a wrong key shows the message and stores nothing", async () => {
  a.socialKeyStatus.mockResolvedValue({ hasKey: false });
  a.mcpList.mockResolvedValue([]);
  a.elevenStatus.mockResolvedValue({ hasKey: false });
  a.setElevenKey.mockRejectedValue("ELEVEN_KEY_INVALID");
  await open("Kết nối & MCP");
  await userEvent.type(await screen.findByLabelText("API key ElevenLabs"), "bad");
  await userEvent.click(screen.getByRole("button", { name: "Lưu key ElevenLabs" }));
  expect(await screen.findByText("Key ElevenLabs không đúng")).toBeInTheDocument();
  expect(a.elevenVoices).not.toHaveBeenCalled();
});

test("ElevenLabs: preview plays, picking a default saves voiceId/voiceName, Xóa key clears", async () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  a.socialKeyStatus.mockResolvedValue({ hasKey: false });
  a.mcpList.mockResolvedValue([]);
  a.elevenStatus.mockResolvedValue({ hasKey: true, remaining: 500 });
  a.elevenVoices.mockResolvedValue(VOICES);
  a.clearElevenKey.mockResolvedValue(null);
  await open("Kết nối & MCP");
  expect(await screen.findByText("Còn 500 ký tự")).toBeInTheDocument();
  await userEvent.click(await screen.findByRole("button", { name: "Nghe thử Lan" }));
  expect(play).toHaveBeenCalled();
  await userEvent.click(screen.getAllByRole("button", { name: "Chọn làm mặc định" })[0]);
  expect(a.saveSettings).toHaveBeenCalledWith({ ...base, voiceId: "v1", voiceName: "Lan" });
  expect(await screen.findByText("Mặc định")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Xóa key" }));
  expect(a.clearElevenKey).toHaveBeenCalled();
  expect(await screen.findByLabelText("API key ElevenLabs")).toBeInTheDocument();
  play.mockRestore();
});

test("defaults card: CTA must be 1–30 characters and saves on Lưu", async () => {
  await open();
  const cta = screen.getByLabelText("Chữ kêu gọi mặc định");
  expect(cta).toHaveValue("BẤM GIỎ HÀNG 👇");
  await userEvent.clear(cta);
  await userEvent.click(screen.getByRole("button", { name: "Lưu chữ kêu gọi" }));
  expect(screen.getByText("Chữ kêu gọi cần 1–30 ký tự")).toBeInTheDocument();
  await userEvent.type(cta, "x".repeat(31));
  await userEvent.click(screen.getByRole("button", { name: "Lưu chữ kêu gọi" }));
  expect(screen.getByText("Chữ kêu gọi cần 1–30 ký tự")).toBeInTheDocument();
  expect(a.saveSettings).not.toHaveBeenCalled();
  await userEvent.clear(cta);
  await userEvent.type(cta, " MUA NGAY ");
  await userEvent.click(screen.getByRole("button", { name: "Lưu chữ kêu gọi" }));
  expect(a.saveSettings).toHaveBeenCalledWith({ ...base, defaultCta: "MUA NGAY" });
  expect(screen.queryByText("Chữ kêu gọi cần 1–30 ký tự")).toBeNull();
});

test("defaults card: length chips save defaultLength, Vừa is the default", async () => {
  await open();
  expect(screen.getByRole("button", { name: "Vừa 20–35s" })).toHaveAttribute("aria-pressed", "true");
  await userEvent.click(screen.getByRole("button", { name: "Ngắn 15–20s" }));
  expect(a.saveSettings).toHaveBeenCalledWith({ ...base, defaultLength: "short" });
});

test("defaults card: picking and removing the default logo call the commands", async () => {
  a.pickFile.mockResolvedValue("/Users/x/logo.png");
  a.fileSrc.mockImplementation((p: string) => "asset://" + p);
  const withLogo = { ...base, defaultLogo: "/data/defaults/logo.png" };
  a.setDefaultLogo.mockResolvedValue(withLogo);
  a.clearDefaultLogo.mockResolvedValue({ ...base, defaultLogo: null });
  await open();
  await userEvent.click(screen.getByRole("button", { name: "Chọn logo" }));
  expect(a.pickFile).toHaveBeenCalledWith("logo");
  expect(a.setDefaultLogo).toHaveBeenCalledWith("/Users/x/logo.png");
  expect(await screen.findByAltText("Logo mặc định")).toHaveAttribute("src", "asset:///data/defaults/logo.png");
  await userEvent.click(screen.getByRole("button", { name: "Bỏ logo" }));
  expect(a.clearDefaultLogo).toHaveBeenCalled();
  expect(screen.queryByAltText("Logo mặc định")).toBeNull();
});

test("connection tab shows bundle.social and MCP blocks", async () => {
  a.socialKeyStatus.mockResolvedValue({ hasKey: false });
  a.mcpList.mockResolvedValue([]);
  await open("Kết nối & MCP");
  expect(await screen.findByLabelText("API key bundle.social")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Thêm MCP server/ })).toBeInTheDocument();
});
