import { vi, test, expect, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { StoreProvider } from "../state/store";
import Onboarding from "./Onboarding";

vi.mock("../lib/api");
vi.mock("../lib/engine");
vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));
const a = vi.mocked(api);
const e = vi.mocked(engine);

let outCb: (o: any) => void; let doneCb: (o: any) => void;
beforeEach(() => {
  vi.clearAllMocks();
  a.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: false });
  a.listProjects.mockResolvedValue([]);
  a.onLoginOutput.mockImplementation(async (cb) => { outCb = cb; return () => {}; });
  a.onLoginDone.mockImplementation(async (cb) => { doneCb = cb; return () => {}; });
});
const mount = () => render(<StoreProvider><Onboarding /></StoreProvider>);

test("step 1 downloads Claude then step 2 shows connected and waits for the model", async () => {
  e.setupCli.mockResolvedValue("/cli/claude");
  let finishModel!: () => void;
  e.setupModel.mockImplementation((onP: any) => { onP?.(0.4); return new Promise<void>((r) => (finishModel = r)); });
  a.authStatus.mockResolvedValue({ source: "claude-code" });
  mount();
  expect(await screen.findByText(/Đã kết nối/)).toBeInTheDocument();
  const start = screen.getByRole("button", { name: "Bắt đầu" });
  expect(start).toBeDisabled();
  expect(screen.getByText(/40%/)).toBeInTheDocument();
  await act(async () => finishModel());
  expect(start).toBeEnabled();
  await userEvent.click(start);
  expect(a.saveSettings).toHaveBeenCalledWith(expect.objectContaining({ onboarded: true }));
});

test("login flow: shows URL button, sends pasted code, confirms with auth-check", async () => {
  e.setupCli.mockResolvedValue("/cli/claude");
  e.setupModel.mockReturnValue(new Promise(() => {}));
  a.authStatus.mockResolvedValue({ source: null });
  a.loginStart.mockResolvedValue(null);
  a.loginInput.mockResolvedValue(null);
  e.authCheck.mockResolvedValue("app-token");
  mount();
  await userEvent.click(await screen.findByRole("button", { name: "Đăng nhập Claude" }));
  expect(a.loginStart).toHaveBeenCalledWith("/cli/claude");
  await waitFor(() => expect(outCb).toBeDefined());
  act(() => outCb({ line: "Open", url: "https://claude.ai/x" }));
  expect(await screen.findByRole("button", { name: "Mở trang đăng nhập" })).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Dán mã từ trình duyệt"), "abc");
  await userEvent.click(screen.getByRole("button", { name: "Gửi" }));
  expect(a.loginInput).toHaveBeenCalledWith("abc");
  await act(async () => doneCb({ ok: true, error: null }));
  expect(e.authCheck).toHaveBeenCalled();
  expect(await screen.findByText(/Đã kết nối/)).toBeInTheDocument();
});

test("setup error shows retry", async () => {
  e.setupCli.mockRejectedValueOnce(new Error("mạng lỗi")).mockResolvedValue("/cli/claude");
  e.setupModel.mockReturnValue(new Promise(() => {}));
  a.authStatus.mockResolvedValue({ source: null });
  mount();
  expect(await screen.findByText("mạng lỗi")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Thử lại" }));
  await waitFor(() => expect(e.setupCli).toHaveBeenCalledTimes(2));
  expect(await screen.findByRole("button", { name: "Đăng nhập Claude" })).toBeInTheDocument();
});
