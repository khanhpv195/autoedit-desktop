import { vi, test, expect, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { localIso } from "../lib/format";
import { StoreProvider, useStore } from "../state/store";
import PostCard from "./PostCard";

vi.mock("../lib/api");
vi.mock("../lib/engine");
const a = vi.mocked(api);
const e = vi.mocked(engine);

const base = { model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true, socialTeamId: "t1", routines: [] };
const account: any = {
  type: "social_account", organization: { name: "O" },
  usage: { posts: { used: 1, limit: 20, remaining: 19 }, uploads: { used: 0, limit: 50, remaining: 50 } },
  teams: [{ id: "t1", name: "T", channels: [
    { type: "TIKTOK", name: "tt", avatar: null, username: null },
    { type: "INSTAGRAM", name: "ig", avatar: null, username: null },
    { type: "TWITTER", name: "x", avatar: null, username: null },
  ] }],
};
const run = { n: 1, final: "/p/1/runs/1/final.mp4", prompt: "p", feedback: null, summary: [], needsReview: false, fallback: false };
const detail = (posts: any[] = []): any => ({
  dir: "/p/1", title: "Váy", niche: "chung", created: "2026-11-20", status: "done", runCount: 1,
  clip: "", logo: null, music: null, prompt: "", scriptCard: null, runs: [run], posts,
});
const post = (over: any = {}) => ({ id: "p1", title: "t", status: "SCHEDULED", postDate: "2026-11-21T19:30:00+07:00", channels: ["TIKTOK"], error: null, project: "1", run: 1, permalinks: {}, ...over });

function Route() { const { state } = useStore(); return <div data-testid="route">{JSON.stringify(state.route)}</div>; }
const mount = (d = detail()) => render(<StoreProvider><PostCard detail={d} run={run} /><Route /></StoreProvider>);

beforeEach(() => {
  vi.clearAllMocks();
  a.getSettings.mockResolvedValue(base);
  a.listProjects.mockResolvedValue([]);
  a.socialKeyStatus.mockResolvedValue({ hasKey: true });
  e.socialCheck.mockResolvedValue(account);
  e.socialCaption.mockResolvedValue("Váy xinh quá #thoitrang");
  e.socialPublish.mockResolvedValue(post({ channels: ["TIKTOK", "INSTAGRAM"] }));
});

test("no key shows the hint and opens settings on the connection tab", async () => {
  a.socialKeyStatus.mockResolvedValue({ hasKey: false });
  mount();
  expect(await screen.findByText(/Bật đăng bài tự động: Cài đặt → Kết nối/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Mở Cài đặt" }));
  expect(screen.getByTestId("route").textContent).toContain('"tab":"conn"');
  expect(e.socialCaption).not.toHaveBeenCalled();
});

test("with a key the AI caption is requested once and filled in; unsupported channels are hidden", async () => {
  mount();
  expect(await screen.findByDisplayValue("Váy xinh quá #thoitrang")).toBeInTheDocument();
  expect(e.socialCaption).toHaveBeenCalledTimes(1);
  expect(e.socialCaption).toHaveBeenCalledWith("/p/1", 1);
  expect(screen.getByText("TikTok")).toBeInTheDocument();
  expect(screen.getByText("Instagram")).toBeInTheDocument();
  expect(screen.queryByText("x")).toBeNull();
});

test("publish now sends the selected channels, caption and when=now, then shows the schedule", async () => {
  mount();
  await screen.findByDisplayValue("Váy xinh quá #thoitrang");
  await userEvent.click(screen.getByRole("button", { name: "Đăng" }));
  expect(e.socialPublish).toHaveBeenCalledWith(
    { dir: "/p/1", run: 1, team: "t1", channels: ["TIKTOK", "INSTAGRAM"], caption: "Váy xinh quá #thoitrang", when: "now" },
    expect.any(Function),
  );
  expect(await screen.findByText(/Đã lên lịch 19:30 21\/11 · TikTok, Instagram/)).toBeInTheDocument();
});

test("pick a time sends an ISO with timezone; queue sends 'queue'", async () => {
  mount();
  await screen.findByDisplayValue("Váy xinh quá #thoitrang");
  await userEvent.click(screen.getByLabelText(/Chọn giờ/, { selector: "input[type=radio]" }));
  fireEvent.change(screen.getByLabelText("Giờ đăng"), { target: { value: "2030-12-01T20:15" } });
  await userEvent.click(screen.getByRole("button", { name: "Đăng" }));
  await waitFor(() => expect(e.socialPublish).toHaveBeenCalled());
  const when = e.socialPublish.mock.calls[0][0].when;
  expect(when).toBe(localIso(new Date("2030-12-01T20:15")));
  expect(when).toMatch(/[+-]\d\d:\d\d$/);

  await userEvent.click(await screen.findByRole("button", { name: "Đăng thêm" }));
  await userEvent.click(screen.getByLabelText(/Vào hàng đợi/, { selector: "input[type=radio]" }));
  await userEvent.click(screen.getByRole("button", { name: "Đăng" }));
  await waitFor(() => expect(e.socialPublish).toHaveBeenCalledTimes(2));
  expect(e.socialPublish.mock.calls[1][0].when).toBe("queue");
});

test("deselecting every channel disables the publish button", async () => {
  mount();
  await screen.findByDisplayValue("Váy xinh quá #thoitrang");
  await userEvent.click(screen.getByText("TikTok"));
  await userEvent.click(screen.getByText("Instagram"));
  expect(screen.getByRole("button", { name: "Đăng" })).toBeDisabled();
});

test("SOCIAL_LIMIT shows the limit message", async () => {
  e.socialPublish.mockRejectedValue({ code: "SOCIAL_LIMIT", message: "429", retry_at: null });
  mount();
  await screen.findByDisplayValue("Váy xinh quá #thoitrang");
  await userEvent.click(screen.getByRole("button", { name: "Đăng" }));
  expect(await screen.findByText("Hết lượt đăng của gói bundle.social")).toBeInTheDocument();
});

test("a run that already has a post shows its status instead of the form, with 'Đăng thêm'", async () => {
  mount(detail([{ id: "p1", run: 1, postDate: "2026-11-21T19:30:00+07:00", channels: ["TIKTOK"], status: "SCHEDULED" }]));
  expect(await screen.findByText(/Đã lên lịch 19:30 21\/11 · TikTok/)).toBeInTheDocument();
  expect(screen.queryByLabelText("Caption")).toBeNull();
  expect(e.socialCaption).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Đăng thêm" }));
  expect(await screen.findByLabelText("Caption")).toBeInTheDocument();
});

test("rewrite asks the AI again", async () => {
  mount();
  await screen.findByDisplayValue("Váy xinh quá #thoitrang");
  e.socialCaption.mockResolvedValue("Bản mới");
  await userEvent.click(screen.getByRole("button", { name: /Viết lại/ }));
  expect(await screen.findByDisplayValue("Bản mới")).toBeInTheDocument();
});
