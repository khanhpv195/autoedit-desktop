import { vi, test, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import ClaudeLogin from "./ClaudeLogin";

vi.mock("../lib/api");
vi.mock("../lib/engine");
vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));
const a = vi.mocked(api);

beforeEach(() => {
  vi.clearAllMocks();
  a.onLoginOutput.mockResolvedValue(() => {});
  a.onLoginDone.mockResolvedValue(() => {});
  a.loginStart.mockResolvedValue(null);
  a.loginCancel.mockResolvedValue(null);
});

test("unmounting during a login cancels the session", async () => {
  const { unmount } = render(<ClaudeLogin cliPath="/c" onConnected={() => {}} />);
  await userEvent.click(screen.getByRole("button", { name: "Đăng nhập Claude" }));
  expect(a.loginStart).toHaveBeenCalledWith("/c");
  unmount();
  expect(a.loginCancel).toHaveBeenCalled();
});

test("unmounting while idle does not cancel anything", () => {
  const { unmount } = render(<ClaudeLogin cliPath="/c" onConnected={() => {}} />);
  unmount();
  expect(a.loginCancel).not.toHaveBeenCalled();
});
