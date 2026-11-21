import { vi, test, expect } from "vitest";
import userEvent from "@testing-library/user-event";
import { act, render, screen } from "@testing-library/react";
import * as api from "./lib/api";
import App from "./App";

vi.mock("./lib/api");
vi.mock("./lib/engine");

test("hiện sidebar khi đã onboard", async () => {
  vi.mocked(api.licenseStatus).mockResolvedValue({ licensed: true, name: "Test" });
  vi.mocked(api.getSettings).mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true });
  vi.mocked(api.listProjects).mockResolvedValue([]);
  render(<App />);
  expect(await screen.findByText("AutoEdit")).toBeInTheDocument();
});

test("chưa kích hoạt: hiện màn hình kích hoạt, không đọc settings", async () => {
  vi.mocked(api.licenseStatus).mockResolvedValue({ licensed: false, name: null });
  vi.mocked(api.getSettings).mockClear();
  render(<App />);
  expect(await screen.findByText("Kích hoạt AutoEdit")).toBeInTheDocument();
  expect(api.getSettings).not.toHaveBeenCalled();
});

test("key bị thu hồi khi đang chạy: khóa app và báo lý do", async () => {
  vi.mocked(api.licenseStatus).mockResolvedValue({ licensed: true, name: "Test" });
  let fire!: (reason: string) => void;
  vi.mocked(api.onLicenseRevoked).mockImplementation(async (cb) => { fire = cb; return () => {}; });
  render(<App />);
  expect(await screen.findByText("AutoEdit")).toBeInTheDocument();
  await act(async () => fire("LICENSE_REVOKED"));
  expect(await screen.findByText("Kích hoạt AutoEdit")).toBeInTheDocument();
  expect(screen.getByText("Key đã bị thu hồi")).toBeInTheDocument();
});

test("kích hoạt thành công: chạy lại boot và vào app", async () => {
  const status = vi.mocked(api.licenseStatus);
  status.mockReset();
  status.mockResolvedValueOnce({ licensed: false, name: null }).mockResolvedValue({ licensed: true, name: "Test" });
  vi.mocked(api.licenseActivate).mockResolvedValue({ licensed: true, name: "Test" });
  vi.mocked(api.getSettings).mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true });
  vi.mocked(api.listProjects).mockResolvedValue([]);
  render(<App />);
  await screen.findByText("Kích hoạt AutoEdit");
  await userEvent.type(screen.getByPlaceholderText("AE-XXXX-XXXX-XXXX-XXXX"), "AE-AAAA-BBBB-CCCC-DDDD");
  await userEvent.click(screen.getByRole("button", { name: "Kích hoạt" }));
  expect(await screen.findByText("AutoEdit")).toBeInTheDocument();
  expect(status).toHaveBeenCalledTimes(2);
  expect(api.getSettings).toHaveBeenCalled();
});
