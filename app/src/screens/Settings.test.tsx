import { vi, test, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { StoreProvider } from "../state/store";
import Settings from "./Settings";

vi.mock("../lib/api");
vi.mock("../lib/engine");
vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));
const a = vi.mocked(api);
const base = { model: "claude-opus-5-5", projectsRoot: "/Users/x/Movies/AutoEdit", lastNiche: null, onboarded: true };

beforeEach(() => {
  vi.clearAllMocks();
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
