import { vi, test, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { openUrl } from "@tauri-apps/plugin-opener";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { StoreProvider, useStore } from "../state/store";
import SocialSettings from "./SocialSettings";

vi.mock("../lib/api");
vi.mock("../lib/engine");
vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));
const a = vi.mocked(api);
const e = vi.mocked(engine);

const base = { model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true, socialTeamId: null, routines: [] };
const account = (teams = 1): any => ({
  type: "social_account",
  organization: { name: "Shop Hoa" },
  usage: { posts: { used: 11, limit: 20, remaining: 9 }, uploads: { used: 3, limit: 50, remaining: 47 } },
  teams: Array.from({ length: teams }, (_, i) => ({
    id: `t${i + 1}`, name: `Team ${i + 1}`,
    channels: [
      { type: "TIKTOK", name: "Shop Hoa", avatar: null, username: "shophoa" },
      { type: "TWITTER", name: "X", avatar: null, username: null },
    ],
  })),
});

beforeEach(() => {
  vi.clearAllMocks();
  a.getSettings.mockResolvedValue(base);
  a.listProjects.mockResolvedValue([]);
  a.saveSettings.mockResolvedValue(null);
  a.setSocialKey.mockResolvedValue(null);
  a.clearSocialKey.mockResolvedValue(null);
  a.socialKeyStatus.mockResolvedValue({ hasKey: false });
});
const mount = () => render(<StoreProvider><SocialSettings /></StoreProvider>);

test("no key: paste + Kiểm tra stores the key, then reads the account and shows quota and channels", async () => {
  e.socialCheck.mockResolvedValue(account());
  mount();
  await userEvent.type(await screen.findByLabelText("API key bundle.social"), "bk-secret");
  await userEvent.click(screen.getByRole("button", { name: "Kiểm tra" }));
  expect(a.setSocialKey).toHaveBeenCalledWith("bk-secret");
  expect(await screen.findByText("Shop Hoa", { selector: "b" })).toBeInTheDocument();
  expect(e.socialCheck).toHaveBeenCalled();
  expect(a.setSocialKey.mock.invocationCallOrder[0]).toBeLessThan(e.socialCheck.mock.invocationCallOrder[0]);
  expect(screen.getByText(/Đã đăng 11\/20 bài tháng này/)).toBeInTheDocument();
  expect(screen.getByText(/@shophoa/)).toBeInTheDocument();
  // unsupported channel is dimmed
  expect(screen.getByText(/chưa hỗ trợ đăng video/).closest(".ch")).toHaveClass("off");
  // a single team is selected automatically
  await waitFor(() => expect(a.saveSettings).toHaveBeenCalledWith(expect.objectContaining({ socialTeamId: "t1" })));
});

test("SOCIAL_AUTH shows 'Key không đúng' and clears the key", async () => {
  e.socialCheck.mockRejectedValue({ code: "SOCIAL_AUTH", message: "x", retry_at: null });
  mount();
  await userEvent.type(await screen.findByLabelText("API key bundle.social"), "bad");
  await userEvent.click(screen.getByRole("button", { name: "Kiểm tra" }));
  expect(await screen.findByText("Key không đúng")).toBeInTheDocument();
  expect(a.clearSocialKey).toHaveBeenCalled();
  expect(screen.getByLabelText("API key bundle.social")).toBeInTheDocument();
});

test("several teams: picking one saves socialTeamId", async () => {
  a.socialKeyStatus.mockResolvedValue({ hasKey: true });
  a.getSettings.mockResolvedValue({ ...base, socialTeamId: "t1" });
  e.socialCheck.mockResolvedValue(account(2));
  mount();
  const sel = await screen.findByLabelText("Team");
  await userEvent.selectOptions(sel, "t2");
  expect(a.saveSettings).toHaveBeenCalledWith(expect.objectContaining({ socialTeamId: "t2" }));
});

test("portal button opens the url; remove key clears it", async () => {
  a.socialKeyStatus.mockResolvedValue({ hasKey: true });
  a.getSettings.mockResolvedValue({ ...base, socialTeamId: "t1" });
  e.socialCheck.mockResolvedValue(account());
  e.socialPortal.mockResolvedValue("https://portal.example/x");
  mount();
  await userEvent.click(await screen.findByRole("button", { name: /Thêm \/ quản lý kênh/ }));
  expect(e.socialPortal).toHaveBeenCalledWith("t1");
  await waitFor(() => expect(openUrl).toHaveBeenCalledWith("https://portal.example/x"));
  await userEvent.click(screen.getByRole("button", { name: "Gỡ key" }));
  expect(a.clearSocialKey).toHaveBeenCalled();
  expect(await screen.findByLabelText("API key bundle.social")).toBeInTheDocument();
});

test("refresh re-reads the account", async () => {
  a.socialKeyStatus.mockResolvedValue({ hasKey: true });
  e.socialCheck.mockResolvedValue(account());
  mount();
  await screen.findByText(/Đã đăng 11/);
  await userEvent.click(screen.getByRole("button", { name: /Làm mới/ }));
  await waitFor(() => expect(e.socialCheck).toHaveBeenCalledTimes(2));
});

test("saving the team uses the newest settings from the store, not a stale copy", async () => {
  a.socialKeyStatus.mockResolvedValue({ hasKey: true });
  let resolve!: (acc: any) => void;
  e.socialCheck.mockReturnValue(new Promise((r) => { resolve = r; }));
  function Bump() { const { dispatch, state } = useStore(); return <button onClick={() => dispatch({ type: "settings", settings: { ...state.settings!, lastNiche: "my-pham" } })}>bump</button>; }
  render(<StoreProvider><SocialSettings /><Bump /></StoreProvider>);
  await waitFor(() => expect(e.socialCheck).toHaveBeenCalled());
  await userEvent.click(screen.getByText("bump"));
  resolve(account());
  await waitFor(() => expect(a.saveSettings).toHaveBeenCalledWith(expect.objectContaining({ socialTeamId: "t1", lastNiche: "my-pham" })));
});
