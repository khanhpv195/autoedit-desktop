import { vi, test, expect, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { localIso, weekRange } from "../lib/format";
import { StoreProvider, useStore } from "../state/store";
import Sidebar from "../components/Sidebar";
import Schedule from "./Schedule";

vi.mock("../lib/api");
vi.mock("../lib/engine");
vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));
const a = vi.mocked(api);
const e = vi.mocked(engine);

// Fri 20 Nov 2026 10:00 local
const NOW = new Date(2026, 10, 20, 10, 0, 0);
const base = { model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true, socialTeamId: "t1", routines: [] as any[] };
const account: any = {
  type: "social_account", organization: { name: "O" },
  usage: { posts: { used: 1, limit: 20, remaining: 19 }, uploads: { used: 0, limit: 50, remaining: 50 } },
  teams: [{ id: "t1", name: "T", channels: [
    { type: "TIKTOK", name: "tt", avatar: null, username: null },
    { type: "YOUTUBE", name: "yt", avatar: null, username: null },
  ] }],
};
const post = (over: any = {}): any => ({
  id: "p1", title: "Váy hoa", status: "SCHEDULED", postDate: localIso(new Date(2026, 10, 21, 19, 30)),
  channels: ["TIKTOK"], error: null, project: null, run: null, permalinks: {}, ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
  a.getSettings.mockResolvedValue(base);
  a.listProjects.mockResolvedValue([]);
  a.saveSettings.mockResolvedValue(null);
  a.socialKeyStatus.mockResolvedValue({ hasKey: true });
  e.socialCheck.mockResolvedValue(account);
  e.socialList.mockResolvedValue([post()]);
  e.routineSync.mockResolvedValue({ created: [post(), post({ id: "p2" })], skipped: null });
});
afterEach(() => vi.useRealTimers());
function Toast() { const { state } = useStore(); return <div>{state.toast}</div>; }
const mount = () => render(<StoreProvider><Schedule /><Toast /></StoreProvider>);

test("locked without a key", async () => {
  a.socialKeyStatus.mockResolvedValue({ hasKey: false });
  mount();
  expect(await screen.findByText("Chưa bật đăng bài tự động")).toBeInTheDocument();
  expect(e.socialList).not.toHaveBeenCalled();
});

test("loads the current week and puts the post in its day column; next week shifts the range", async () => {
  mount();
  const { from, to } = weekRange(NOW, 0);
  await waitFor(() => expect(e.socialList).toHaveBeenCalledWith("t1", localIso(from), localIso(to)));
  expect(from.getDay()).toBe(1);
  const sat = await screen.findByTestId("day-T7");
  expect(within(sat).getByText(/19:30/)).toBeInTheDocument();
  expect(within(screen.getByTestId("day-T6")).queryByText(/19:30/)).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: /Tuần sau/ }));
  const next = weekRange(NOW, 1);
  await waitFor(() => expect(e.socialList).toHaveBeenLastCalledWith("t1", localIso(next.from), localIso(next.to)));
});

test("an ERROR post shows its error and Thử lại calls socialRetry", async () => {
  e.socialList.mockResolvedValue([post({ status: "ERROR", error: "Token hết hạn" })]);
  e.socialRetry.mockResolvedValue(post({ status: "SCHEDULED" }));
  mount();
  await userEvent.click(await screen.findByRole("button", { name: /Bài 19:30/ }));
  expect(screen.getByText("Token hết hạn")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Thử lại" }));
  expect(e.socialRetry).toHaveBeenCalledWith("p1");
});

test("list mode shows posts by day", async () => {
  mount();
  await screen.findByTestId("day-T7");
  await userEvent.click(screen.getByRole("button", { name: "Danh sách" }));
  expect(await screen.findByRole("button", { name: /Bài 19:30/ })).toBeInTheDocument();
});

test("adding a routine saves settings; Chạy ngay runs routine-sync and reports the count", async () => {
  mount();
  await screen.findByTestId("day-T7");
  await waitFor(() => expect(e.socialCheck).toHaveBeenCalled());
  await new Promise((r) => setTimeout(r, 10));
  await userEvent.click(screen.getByRole("button", { name: "＋ Thêm routine" }));
  await waitFor(() => expect(a.saveSettings).toHaveBeenCalled());
  const saved: any = a.saveSettings.mock.calls[0][0];
  expect(saved.routines).toHaveLength(1);
  expect(saved.routines[0]).toMatchObject({ time: "19:30", enabled: true, channels: ["TIKTOK", "YOUTUBE"] });
  fireEvent.change(screen.getByLabelText("Giờ routine 1"), { target: { value: "08:15" } });
  await waitFor(() => expect((a.saveSettings.mock.calls.at(-1)![0] as any).routines[0].time).toBe("08:15"));
  await userEvent.click(screen.getByRole("button", { name: "Chạy ngay" }));
  expect(e.routineSync).toHaveBeenCalledWith("t1");
  expect(await screen.findByText("Đã tạo 2 bài cho 7 ngày tới")).toBeInTheDocument();
});

test("sidebar: Lịch đăng is dim without a key and enabled with one", async () => {
  a.socialKeyStatus.mockResolvedValue({ hasKey: false });
  const { unmount } = render(<StoreProvider><Sidebar /></StoreProvider>);
  const off = (await screen.findByText(/Lịch đăng/)).closest(".sn")!;
  expect(off).toHaveAttribute("aria-disabled", "true");
  unmount();
  a.socialKeyStatus.mockResolvedValue({ hasKey: true });
  render(<StoreProvider><Sidebar /></StoreProvider>);
  await waitFor(() => expect(screen.getByText(/Lịch đăng/).closest(".sn")).not.toHaveAttribute("aria-disabled"));
});

test("key present but the account read failed: error panel, not the 'no key' screen", async () => {
  e.socialCheck.mockRejectedValue({ code: "SOCIAL_AUTH", message: "401", retry_at: null });
  a.getSettings.mockResolvedValue({ ...base, socialTeamId: null });
  mount();
  expect(await screen.findByText("Key bundle.social không dùng được")).toBeInTheDocument();
  expect(screen.queryByText("Chưa bật đăng bài tự động")).toBeNull();
  expect(screen.getByRole("button", { name: /Mở Cài đặt → Kết nối/ })).toBeInTheDocument();
});

test("key present but zero teams: says so", async () => {
  e.socialCheck.mockResolvedValue({ ...account, teams: [] });
  a.getSettings.mockResolvedValue({ ...base, socialTeamId: null });
  mount();
  expect(await screen.findByText("Chưa có team trên bundle.social")).toBeInTheDocument();
  expect(screen.queryByText("Chưa bật đăng bài tự động")).toBeNull();
});

test("Chạy ngay shows the engine's 'skipped' text and is disabled while a sync runs", async () => {
  let finish!: (r: any) => void;
  e.routineSync.mockReturnValue(new Promise((res) => { finish = res; }));
  mount();
  await screen.findByTestId("day-T7");
  await userEvent.click(screen.getByRole("button", { name: "Chạy ngay" }));
  expect(await screen.findByRole("button", { name: "Đang chạy…" })).toBeDisabled();
  finish({ created: [], skipped: "Routine đang chạy" });
  expect(await screen.findByText("Routine đang chạy")).toBeInTheDocument();
});
