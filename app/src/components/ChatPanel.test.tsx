import { vi, test, expect, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import ChatPanel from "./ChatPanel";
import type { ChatMessage, ChatPlan } from "../lib/types";

vi.mock("../lib/api");
vi.mock("../lib/engine");
const a = vi.mocked(api);
const e = vi.mocked(engine);

type Reply = Extract<ChatMessage, { role: "assistant" }>;
const plan = (prompt: string): ChatPlan => ({
  summary: [`Thời lượng: ~30s — ${prompt}`, "Hook: GIÁ CHỈ 199K"], prompt, target_seconds: [27, 33],
  length_source: "ai", length_reason: "đủ 3 ý", hook: "GIÁ CHỈ 199K", cta: "BẤM GIỎ HÀNG",
});
const reply = (text: string, extra: Partial<Reply> = {}): Reply =>
  ({ role: "assistant", text, suggestions: [], plan: null, ts: 1, ...extra });

const prepare = vi.fn(async () => "/proj/1" as string | null);
const onStart = vi.fn();
const mount = (props: Partial<Parameters<typeof ChatPanel>[0]> = {}) =>
  render(<ChatPanel dir="/proj/1" busy={false} prepare={prepare} onStart={onStart} onSettings={() => {}} onSetup={() => {}} {...props} />);
const box = () => screen.getByLabelText("Tin nhắn cho AI");

beforeEach(() => {
  vi.clearAllMocks();
  prepare.mockResolvedValue("/proj/1");
  a.readChat.mockResolvedValue([]);
  e.chat.mockResolvedValue(reply("Clip có 1 người nói, khoảng 48s lời.", { suggestions: ["Giữ trọn lời", "Rút còn ~30s"] }));
});

test("an empty chat opens itself once: the AI describes the clips and offers quick replies", async () => {
  mount();
  expect(await screen.findByText("Clip có 1 người nói, khoảng 48s lời.")).toBeInTheDocument();
  expect(prepare).toHaveBeenCalledTimes(1);
  expect(e.chat).toHaveBeenCalledTimes(1);
  expect(e.chat).toHaveBeenCalledWith("/proj/1", "", expect.any(Function), expect.any(Function));
  expect(screen.getByRole("button", { name: "Rút còn ~30s" })).toBeInTheDocument();
});

test("no opening turn while files are still being copied, nor without a project", async () => {
  const { rerender } = mount({ busy: true });
  await waitFor(() => expect(a.readChat).toHaveBeenCalled());
  expect(e.chat).not.toHaveBeenCalled();
  rerender(<ChatPanel dir={null} busy={false} prepare={prepare} onStart={onStart} onSettings={() => {}} onSetup={() => {}} />);
  expect(screen.getByText("Thêm clip để trò chuyện với AI về cách dựng")).toBeInTheDocument();
  expect(e.chat).not.toHaveBeenCalled();
});

test("a saved chat is shown again and not re-opened; only the latest plan can be started", async () => {
  a.readChat.mockResolvedValue([
    reply("Chào anh/chị"),
    { role: "user", text: "30s", ts: 2 },
    reply("Kế hoạch 1", { plan: plan("bản cũ") }),
    { role: "user", text: "đổi hook", ts: 4 },
    reply("Kế hoạch 2", { plan: plan("bản mới") }),
  ]);
  mount();
  expect(await screen.findByText("Kế hoạch 2")).toBeInTheDocument();
  expect(screen.getByText("đổi hook")).toBeInTheDocument();
  expect(screen.getByText("Kế hoạch cũ")).toBeInTheDocument();
  const start = screen.getAllByRole("button", { name: "Bắt đầu edit" });
  expect(start).toHaveLength(1);
  await userEvent.click(start[0]);
  expect(onStart).toHaveBeenCalledWith(plan("bản mới"));
  expect(e.chat).not.toHaveBeenCalled();
});

test("Enter sends, Shift+Enter adds a line; the reply with a plan shows Bắt đầu edit", async () => {
  a.readChat.mockResolvedValue([reply("Chào anh/chị")]);
  e.chat.mockResolvedValue(reply("Đây là kế hoạch", { plan: plan("cắt còn 30s") }));
  mount();
  await screen.findByText("Chào anh/chị");
  await userEvent.type(box(), "cắt còn 30s{Shift>}{Enter}{/Shift}mở bằng giá");
  expect(e.chat).not.toHaveBeenCalled();
  await userEvent.keyboard("{Enter}");
  expect(e.chat).toHaveBeenCalledWith("/proj/1", "cắt còn 30s\nmở bằng giá", expect.any(Function), expect.any(Function));
  expect(await screen.findByText("Đây là kế hoạch")).toBeInTheDocument();
  expect(screen.getByText("cắt còn 30s\nmở bằng giá", { normalizer: (s) => s })).toBeInTheDocument();
  expect(box()).toHaveValue("");
  expect(screen.getByRole("button", { name: "Bắt đầu edit" })).toBeEnabled();
});

test("a quick reply is sent as the customer's message", async () => {
  mount();
  await userEvent.click(await screen.findByRole("button", { name: "Rút còn ~30s" }));
  expect(e.chat).toHaveBeenLastCalledWith("/proj/1", "Rút còn ~30s", expect.any(Function), expect.any(Function));
});

test("a failed turn puts the message back in the box and offers to send it again", async () => {
  a.readChat.mockResolvedValue([reply("Chào anh/chị")]);
  e.chat.mockRejectedValueOnce({ code: "AGENT_FAILED", message: "AI không trả lời được", retry_at: null });
  mount();
  await screen.findByText("Chào anh/chị");
  await userEvent.type(box(), "làm 45s{Enter}");
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(box()).toHaveValue("làm 45s");
  expect(screen.queryByText("làm 45s", { selector: ".bubble" })).toBeNull();
  e.chat.mockResolvedValue(reply("OK 45s"));
  await userEvent.click(screen.getByRole("button", { name: "Gửi lại" }));
  expect(await screen.findByText("OK 45s")).toBeInTheDocument();
  expect(e.chat).toHaveBeenLastCalledWith("/proj/1", "làm 45s", expect.any(Function), expect.any(Function));
});

test("Dừng cancels the turn without an error; the message goes back to the box", async () => {
  a.readChat.mockResolvedValue([reply("Chào anh/chị")]);
  let fail!: (e: unknown) => void;
  const cancel = vi.fn(async () => { fail({ code: "AGENT_FAILED", message: "", retry_at: null }); });
  e.chat.mockImplementation((async (_d: string, _t: string, onEvent?: (ev: unknown) => void, onJob?: (j: unknown) => void) => {
    onJob?.({ cancel, result: new Promise(() => {}) });
    onEvent?.({ type: "step", label: "Đang nghe lời thoại…", progress: 0.1 });
    return new Promise((_r, rej) => { fail = rej; });
  }) as never);
  mount();
  await screen.findByText("Chào anh/chị");
  await userEvent.type(box(), "ngắn thôi{Enter}");
  expect(await screen.findByText(/Đang nghe lời thoại/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Dừng" }));
  expect(cancel).toHaveBeenCalled();
  await waitFor(() => expect(box()).toHaveValue("ngắn thôi"));
  expect(screen.queryByRole("alert")).toBeNull();
});

test("nothing is sent when the project sync failed (prepare returns null)", async () => {
  a.readChat.mockResolvedValue([reply("Chào anh/chị")]);
  prepare.mockResolvedValue(null);
  mount();
  await screen.findByText("Chào anh/chị");
  await userEvent.type(box(), "ngắn thôi{Enter}");
  await act(async () => {});
  expect(e.chat).not.toHaveBeenCalled();
});

test("the turn is cancelled when the panel unmounts", async () => {
  const cancel = vi.fn(async () => {});
  e.chat.mockImplementation((async (_d: string, _t: string, _ev: unknown, onJob?: (j: unknown) => void) => {
    onJob?.({ cancel, result: new Promise(() => {}) });
    return new Promise(() => {});
  }) as never);
  const { unmount } = mount();
  await screen.findByText(/AI đang trả lời/);
  unmount();
  expect(cancel).toHaveBeenCalled();
});
