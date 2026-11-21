import { vi, test, expect, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { StoreProvider, useStore } from "../state/store";
import NewVideo from "./NewVideo";
import type { ProjectDetail } from "../lib/types";

vi.mock("../lib/api");
vi.mock("../lib/engine");
let dropHandler: ((e: { payload: unknown }) => void) | null = null;
vi.mock("@tauri-apps/api/webview", () => ({
  getCurrentWebview: () => ({
    onDragDropEvent: async (cb: (e: { payload: unknown }) => void) => { dropHandler = cb; return () => {}; },
  }),
}));
const a = vi.mocked(api);
const e = vi.mocked(engine);
const cards = [1, 2, 3].map((i) => ({ title: `Ý ${i}`, hook: `Hook ${i}`, outline: `Outline ${i}`, prompt: `Prompt ${i}` }));

function Probe() { const { state } = useStore(); return <div data-testid="r">{JSON.stringify([state.route, state.pendingEdit])}</div>; }
const mount = () => render(<StoreProvider><NewVideo niche="my-pham" /><Probe /></StoreProvider>);

const detail = (clips: string[], images: string[], extra: Partial<ProjectDetail> = {}): ProjectDetail => ({
  dir: "/proj/1", title: "a", niche: "my-pham", created: "2026-11-20", status: "new", runCount: 0,
  clips, images, logo: null, music: null, prompt: "", scriptCard: null, runs: [], ...extra,
});
const inp = (n: string) => `/proj/1/input/${n}`;
const AI = "✨ AI gợi ý kịch bản";
const CTA = "BẤM GIỎ HÀNG 👇";

beforeEach(() => {
  vi.clearAllMocks();
  dropHandler = null;
  a.licenseStatus.mockResolvedValue({ licensed: true, name: "Test" });
  a.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true });
  a.listProjects.mockResolvedValue([]);
  a.pickMedia.mockResolvedValue(["/v/a.mp4"]);
  a.createProject.mockResolvedValue({ dir: "/proj/1", title: "a", niche: "my-pham", created: "2026-11-20", status: "new", runCount: 0 });
  a.getProject.mockResolvedValue(detail([inp("a.mp4")], []));
  a.setProjectMedia.mockImplementation(async (_d, c, i) => detail(c.map((p) => inp(p.split("/").pop()!)), i.map((p) => inp(p.split("/").pop()!))));
  a.updateProject.mockResolvedValue(null);
});

async function addFirst() {
  await userEvent.click(await screen.findByText("Kéo clip và ảnh vào đây"));
  await screen.findByText("1. a.mp4");
}

test("picking a clip creates the project but does NOT analyze; the button does", async () => {
  e.analyze.mockResolvedValue(cards);
  mount();
  await addFirst();
  expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4"], [], null, null, CTA, "medium");
  expect(e.analyze).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: AI }));
  expect(e.analyze).toHaveBeenCalledWith("/proj/1", [], expect.any(Function), expect.any(Function));
  expect(await screen.findByText("Ý 2")).toBeInTheDocument();
  await userEvent.click(screen.getByText("Ý 2"));
  expect(screen.getByRole("textbox")).toHaveValue("Prompt 2");
  expect(a.updateProject).toHaveBeenCalledWith("/proj/1", { script_card: cards[1] });
  await userEvent.click(screen.getByText("↻ Gợi ý khác"));
  expect(e.analyze).toHaveBeenLastCalledWith("/proj/1", ["Ý 1", "Ý 2", "Ý 3"], expect.any(Function), expect.any(Function));
});

test("the suggestion button is disabled until a project exists", async () => {
  mount();
  expect(await screen.findByRole("button", { name: AI })).toBeDisabled();
});

test("multi-drop sorts clips and images, ignores other files, passes images to create", async () => {
  mount();
  await screen.findByText("Kéo clip và ảnh vào đây");
  await waitFor(() => expect(dropHandler).not.toBeNull());
  a.getProject.mockResolvedValue(detail([inp("a.mp4"), inp("b.mov")], [inp("x.png")]));
  // jsdom rects are all zero, so a (0,0) drop counts as inside
  act(() => dropHandler!({ payload: { type: "drop", position: { x: 0, y: 0 }, paths: ["/v/a.mp4", "/v/x.png", "/v/b.mov", "/v/notes.txt"] } }));
  expect(await screen.findByText("1. a.mp4")).toBeInTheDocument();
  expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4", "/v/b.mov"], ["/v/x.png"], null, null, CTA, "medium");
  expect(await screen.findByText("x.png")).toBeInTheDocument();
  expect(screen.getByText("2. b.mov")).toBeInTheDocument();
});

test("images added first are held; the project is created when the first clip arrives", async () => {
  mount();
  await screen.findByText("Kéo clip và ảnh vào đây");
  await waitFor(() => expect(dropHandler).not.toBeNull());
  act(() => dropHandler!({ payload: { type: "drop", position: { x: 0, y: 0 }, paths: ["/v/x.png"] } }));
  expect(await screen.findByText("x.png")).toBeInTheDocument();
  expect(a.createProject).not.toHaveBeenCalled();
  await userEvent.click(screen.getByText("+ Thêm file"));
  await waitFor(() => expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4"], ["/v/x.png"], null, null, CTA, "medium"));
});

test("reorder and remove call set_project_media; the last clip cannot be removed", async () => {
  mount();
  await addFirst();
  a.pickMedia.mockResolvedValue(["/v/b.mov", "/v/x.png"]);
  await userEvent.click(screen.getByText("+ Thêm file"));
  await screen.findByText("2. b.mov");
  expect(a.setProjectMedia).toHaveBeenLastCalledWith("/proj/1", [inp("a.mp4"), "/v/b.mov"], ["/v/x.png"]);
  await waitFor(() => expect(screen.getByRole("button", { name: "Lên b.mov" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Lên b.mov" }));
  await waitFor(() => expect(a.setProjectMedia).toHaveBeenLastCalledWith("/proj/1", [inp("b.mov"), inp("a.mp4")], [inp("x.png")]));
  await userEvent.click(screen.getByRole("button", { name: "Xóa ảnh x.png" }));
  await waitFor(() => expect(a.setProjectMedia).toHaveBeenLastCalledWith("/proj/1", expect.any(Array), []));
  await userEvent.click(screen.getByRole("button", { name: "Xóa b.mov" }));
  await waitFor(() => expect(a.setProjectMedia).toHaveBeenLastCalledWith("/proj/1", [inp("a.mp4")], []));
  expect(screen.getByRole("button", { name: "Xóa a.mp4" })).toBeDisabled();
});

test("changing media clears shown suggestions", async () => {
  e.analyze.mockResolvedValue(cards);
  mount();
  await addFirst();
  await userEvent.click(screen.getByRole("button", { name: AI }));
  await screen.findByText("Ý 1");
  a.pickMedia.mockResolvedValue(["/v/b.mov"]);
  await userEvent.click(screen.getByText("+ Thêm file"));
  await waitFor(() => expect(screen.queryByText("Ý 1")).toBeNull());
  expect(screen.getByRole("button", { name: AI })).toBeEnabled();
});

test("clip count is capped at 10", async () => {
  mount();
  await screen.findByText("Kéo clip và ảnh vào đây");
  a.pickMedia.mockResolvedValue(Array.from({ length: 12 }, (_, i) => `/v/c${i}.mp4`));
  a.getProject.mockResolvedValue(detail(Array.from({ length: 10 }, (_, i) => inp(`c${i}.mp4`)), []));
  await userEvent.click(screen.getByText("Kéo clip và ảnh vào đây"));
  await waitFor(() => expect(a.createProject).toHaveBeenCalled());
  expect(a.createProject.mock.calls[0][1]).toHaveLength(10);
});

test("build dispatches route project with pendingEdit", async () => {
  e.analyze.mockResolvedValue(cards);
  mount();
  await addFirst();
  await userEvent.click(screen.getByRole("button", { name: AI }));
  await screen.findByText("Ý 1");
  await userEvent.click(screen.getByText("Ý 1"));
  await userEvent.click(screen.getByRole("button", { name: "Dựng video" }));
  expect(a.updateProject).toHaveBeenCalledWith("/proj/1", { prompt: "Prompt 1" });
  const r = JSON.parse(screen.getByTestId("r").textContent!);
  expect(r[0]).toEqual({ name: "project", dir: "/proj/1" });
  expect(r[1]).toMatchObject({ dir: "/proj/1", prompt: "Prompt 1" });
});

test("analyze error still allows building with a typed prompt", async () => {
  e.analyze.mockRejectedValue({ code: "RATE_LIMIT", message: "", retry_at: null });
  mount();
  await addFirst();
  await userEvent.click(screen.getByRole("button", { name: AI }));
  expect(await screen.findByText("Đã hết lượt Claude")).toBeInTheDocument();
  const btn = screen.getByRole("button", { name: "Dựng video" });
  expect(btn).toBeDisabled();
  await userEvent.type(screen.getByRole("textbox"), "ngắn thôi");
  expect(btn).toBeEnabled();
});

test("analyze job is cancelled when the screen unmounts", async () => {
  const cancel = vi.fn(async () => {});
  e.analyze.mockImplementation((async (_d: string, _x: string[], _ev: unknown, onJob?: (j: unknown) => void) => {
    onJob?.({ cancel, result: new Promise(() => {}) });
    return new Promise(() => {});
  }) as never);
  const { unmount } = mount();
  await addFirst();
  await userEvent.click(screen.getByRole("button", { name: AI }));
  await screen.findByText(/AI đang xem clip/);
  unmount();
  expect(cancel).toHaveBeenCalled();
});

test("a failed analyze offers retry and setup", async () => {
  e.analyze.mockRejectedValueOnce({ code: "AGENT_FAILED", message: "hỏng", retry_at: null });
  mount();
  await addFirst();
  await userEvent.click(screen.getByRole("button", { name: AI }));
  e.analyze.mockResolvedValue(cards);
  await userEvent.click(await screen.findByRole("button", { name: "Dựng lại" }));
  expect(await screen.findByText("Ý 1")).toBeInTheDocument();
});

test("opened for an existing project: loads clips/images and saved card, no auto-analyze, no new project", async () => {
  a.getProject.mockResolvedValue(detail([inp("a.mp4"), inp("b.mp4")], [inp("x.png")], { dir: "/proj/9", scriptCard: cards[1] }));
  render(<StoreProvider><NewVideo niche="my-pham" dir="/proj/9" /><Probe /></StoreProvider>);
  expect(await screen.findByText("Ý 2")).toBeInTheDocument();
  expect(screen.getByText("2. b.mp4")).toBeInTheDocument();
  expect(screen.getByText("x.png")).toBeInTheDocument();
  expect(screen.getByRole("textbox")).toHaveValue("Prompt 2");
  await userEvent.click(screen.getByRole("button", { name: "Dựng video" }));
  expect(a.createProject).not.toHaveBeenCalled();
  expect(e.analyze).not.toHaveBeenCalled();
  expect(a.updateProject).toHaveBeenCalledWith("/proj/9", { prompt: "Prompt 2" });
  expect(JSON.parse(screen.getByTestId("r").textContent!)[0]).toEqual({ name: "project", dir: "/proj/9" });
});

test("existing project without a saved card does not auto-analyze", async () => {
  a.getProject.mockResolvedValue(detail([inp("a.mp4")], [], { dir: "/proj/9" }));
  render(<StoreProvider><NewVideo niche="my-pham" dir="/proj/9" /><Probe /></StoreProvider>);
  expect(await screen.findByText("1. a.mp4")).toBeInTheDocument();
  expect(e.analyze).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: AI })).toBeEnabled();
});

function deferred<T>() {
  let resolve!: (v: T) => void, reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
const summary = { dir: "/proj/1", title: "a", niche: "my-pham", created: "2026-11-20", status: "new" as const, runCount: 0 };

test("build and AI are disabled while a media sync is pending", async () => {
  mount();
  await addFirst();
  await waitFor(() => expect(screen.getByRole("button", { name: AI })).toBeEnabled());
  const slow = deferred<ProjectDetail>();
  a.setProjectMedia.mockReturnValueOnce(slow.promise);
  a.pickMedia.mockResolvedValue(["/v/big.mov"]);
  await userEvent.type(screen.getByRole("textbox"), "ngắn thôi");
  await waitFor(() => expect(screen.getByRole("button", { name: "Dựng video" })).toBeEnabled());
  await userEvent.click(screen.getByText("+ Thêm file"));
  await waitFor(() => expect(screen.getByRole("button", { name: "Dựng video" })).toBeDisabled());
  expect(screen.getByRole("button", { name: AI })).toBeDisabled();
  expect(screen.getAllByText("Đang chép file…").length).toBeGreaterThan(0);
  await act(async () => { slow.resolve(detail([inp("a.mp4"), inp("big.mov")], [])); });
  await waitFor(() => expect(screen.getByRole("button", { name: "Dựng video" })).toBeEnabled());
  expect(screen.getByRole("button", { name: AI })).toBeEnabled();
});

test("a failed media sync blocks build and does not start the engine", async () => {
  mount();
  await addFirst();
  a.setProjectMedia.mockRejectedValueOnce({ code: "UNKNOWN", message: "đầy ổ đĩa", retry_at: null });
  a.pickMedia.mockResolvedValue(["/v/big.mov"]);
  await userEvent.type(screen.getByRole("textbox"), "ngắn thôi");
  await userEvent.click(screen.getByText("+ Thêm file"));
  await waitFor(() => expect(a.setProjectMedia).toHaveBeenCalled());
  await waitFor(() => expect(screen.getByRole("button", { name: "Dựng video" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Dựng video" }));
  expect(a.updateProject).not.toHaveBeenCalled();
  expect(JSON.parse(screen.getByTestId("r").textContent!)[0]).not.toMatchObject({ name: "project" });
  await userEvent.click(screen.getByRole("button", { name: AI }));
  expect(e.analyze).not.toHaveBeenCalled();
});

test("analyze results for old media are dropped when media changes mid-run", async () => {
  const run = deferred<typeof cards>();
  const cancel = vi.fn(async () => {});
  e.analyze.mockImplementation((async (_d: string, _x: string[], _ev: unknown, onJob?: (j: unknown) => void) => {
    onJob?.({ cancel, result: run.promise });
    return run.promise;
  }) as never);
  mount();
  await addFirst();
  await waitFor(() => expect(screen.getByRole("button", { name: AI })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: AI }));
  await screen.findByText(/AI đang xem clip/);
  a.pickMedia.mockResolvedValue(["/v/b.mov"]);
  await userEvent.click(screen.getByText("+ Thêm file"));
  expect(cancel).toHaveBeenCalled();
  await act(async () => { run.resolve(cards); });
  expect(screen.queryByText("Ý 1")).toBeNull();
  await waitFor(() => expect(screen.getByRole("button", { name: AI })).toBeEnabled());
});

test("analyze errors for old media are dropped too", async () => {
  const run = deferred<typeof cards>();
  e.analyze.mockImplementation((async () => run.promise) as never);
  mount();
  await addFirst();
  await waitFor(() => expect(screen.getByRole("button", { name: AI })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: AI }));
  await screen.findByText(/AI đang xem clip/);
  a.pickMedia.mockResolvedValue(["/v/b.mov"]);
  await userEvent.click(screen.getByText("+ Thêm file"));
  await act(async () => { run.reject({ code: "AGENT_FAILED", message: "hỏng", retry_at: null }); });
  expect(screen.queryByText("Dựng lại")).toBeNull();
});

test("sources added while create is in flight are mapped to input copies, and re-adding is deduped", async () => {
  const create = deferred<typeof summary>();
  a.createProject.mockReturnValueOnce(create.promise);
  mount();
  await addFirst();
  a.pickMedia.mockResolvedValue(["/v/b.mov"]);
  await userEvent.click(screen.getByText("+ Thêm file"));
  await screen.findByText("2. b.mov");
  await act(async () => { create.resolve(summary); });
  await waitFor(() => expect(a.setProjectMedia).toHaveBeenCalled());
  expect(a.setProjectMedia).toHaveBeenLastCalledWith("/proj/1", [inp("a.mp4"), "/v/b.mov"], []);
  a.pickMedia.mockResolvedValue(["/v/a.mp4"]);
  const before = a.setProjectMedia.mock.calls.length;
  await userEvent.click(screen.getByText("+ Thêm file"));
  expect(a.setProjectMedia.mock.calls.length).toBe(before);
  expect(screen.queryByText("3. a.mp4")).toBeNull();
});

test("a logo picked while the project is being created is sent after create", async () => {
  const create = deferred<typeof summary>();
  a.createProject.mockReturnValueOnce(create.promise);
  a.pickFile.mockResolvedValue("/v/logo.png");
  a.setProjectAsset.mockResolvedValue(detail([inp("a.mp4")], [], { logo: inp("logo.png") }));
  mount();
  await addFirst();
  await userEvent.click(screen.getByText("Logo (tùy chọn)"));
  await waitFor(() => expect(a.pickFile).toHaveBeenCalled());
  expect(a.setProjectAsset).not.toHaveBeenCalled();
  await act(async () => { create.resolve(summary); });
  await waitFor(() => expect(a.setProjectAsset).toHaveBeenCalledTimes(1));
  expect(a.setProjectAsset).toHaveBeenCalledWith("/proj/1", "logo", "/v/logo.png");
  expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4"], [], null, null, CTA, "medium");
});

const VOICE_SETTINGS = { model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true, voiceId: "v1", voiceName: "Lan" };
const VOICES = [
  { id: "v1", name: "Lan", labels: {}, previewUrl: null },
  { id: "v2", name: "Minh", labels: {}, previewUrl: null },
];
const TOGGLE = "🎙 Lồng tiếng AI";

test("voiceover toggle is disabled without a key and links to Settings", async () => {
  a.elevenStatus.mockResolvedValue({ hasKey: false });
  mount();
  const link = await screen.findByRole("button", { name: "Nhập key ở Cài đặt" });
  expect(screen.getByRole("checkbox", { name: TOGGLE })).toBeDisabled();
  await userEvent.click(link);
  expect(JSON.parse(screen.getByTestId("r").textContent!)[0]).toEqual({ name: "settings", tab: "conn" });
});

test("voiceover toggle is disabled with a key but no default voice", async () => {
  a.elevenStatus.mockResolvedValue({ hasKey: true, remaining: 1000 });
  mount();
  expect(await screen.findByRole("button", { name: "Chọn giọng mặc định ở Cài đặt" })).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: TOGGLE })).toBeDisabled();
});

test("turning voiceover on shows voice + product info, and build saves them", async () => {
  a.getSettings.mockResolvedValue(VOICE_SETTINGS);
  a.elevenStatus.mockResolvedValue({ hasKey: true, remaining: 1000 });
  a.elevenVoices.mockResolvedValue(VOICES);
  a.setProjectVoiceover.mockResolvedValue(detail([inp("a.mp4")], []));
  mount();
  await addFirst();
  const toggle = await screen.findByRole("checkbox", { name: TOGGLE });
  await waitFor(() => expect(toggle).toBeEnabled());
  expect(screen.queryByLabelText("Thông tin sản phẩm")).toBeNull();
  await userEvent.click(toggle);
  const voice = await screen.findByLabelText("Giọng đọc");
  expect(voice).toHaveValue("v1");
  await screen.findByRole("option", { name: "Minh" });
  await userEvent.selectOptions(voice, "v2");
  const info = screen.getByLabelText("Thông tin sản phẩm");
  expect(info).toHaveAttribute("maxLength", "500");
  await userEvent.type(info, "Áo lụa 199k");
  expect(screen.getByText("11/500")).toBeInTheDocument();
  await userEvent.type(screen.getByPlaceholderText(/Ví dụ/), "ngắn gọn");
  await userEvent.click(screen.getByRole("button", { name: "Dựng video" }));
  expect(a.setProjectVoiceover).toHaveBeenCalledWith("/proj/1", { enabled: true, voiceId: "v2", voiceName: "Minh" }, "Áo lụa 199k");
  expect(JSON.parse(screen.getByTestId("r").textContent!)[0]).toEqual({ name: "project", dir: "/proj/1" });
});

test("with voiceover off, build clears it", async () => {
  a.setProjectVoiceover.mockResolvedValue(detail([inp("a.mp4")], []));
  mount();
  await addFirst();
  await userEvent.type(screen.getByPlaceholderText(/Ví dụ/), "ngắn gọn");
  await userEvent.click(screen.getByRole("button", { name: "Dựng video" }));
  expect(a.setProjectVoiceover).toHaveBeenCalledWith("/proj/1", null, "");
});

test("length chips are pre-filled from settings, sent to create, and saved when changed", async () => {
  a.getSettings.mockResolvedValue({ ...VOICE_SETTINGS, defaultLength: "long", defaultCta: "MUA NGAY" });
  mount();
  await waitFor(() => expect(screen.getByRole("button", { name: "Dài 35–60s" })).toHaveAttribute("aria-pressed", "true"));
  await addFirst();
  expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4"], [], null, null, "MUA NGAY", "long");
  await userEvent.click(screen.getByRole("button", { name: "Ngắn 15–20s" }));
  await waitFor(() => expect(a.updateProject).toHaveBeenCalledWith("/proj/1", { length: "short" }));
  expect(screen.getByRole("button", { name: "Ngắn 15–20s" })).toHaveAttribute("aria-pressed", "true");
});

test("the default logo is pre-filled and can be removed for this video", async () => {
  a.getSettings.mockResolvedValue({ ...VOICE_SETTINGS, defaultLogo: "/data/defaults/logo.png" });
  mount();
  expect(await screen.findByText("logo.png")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Bỏ logo" }));
  expect(screen.queryByText("logo.png")).toBeNull();
  await addFirst();
  expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4"], [], null, null, CTA, "medium");
});

test("the default logo goes to create when kept", async () => {
  a.getSettings.mockResolvedValue({ ...VOICE_SETTINGS, defaultLogo: "/data/defaults/logo.png" });
  mount();
  await screen.findByText("logo.png");
  await addFirst();
  expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4"], [], "/data/defaults/logo.png", null, CTA, "medium");
});

test("card outline renders one list item per step (string fallback for old cards)", async () => {
  e.analyze.mockResolvedValue([
    { title: "A", hook: "H", outline: ["Mở bằng cảnh xoay", "Cận chất vải", "Chốt giỏ hàng"], prompt: "p" },
    { title: "B", hook: "H", outline: "Một bước cũ", prompt: "p" },
  ]);
  mount();
  await addFirst();
  await userEvent.click(screen.getByRole("button", { name: AI }));
  await screen.findByText("A");
  const lists = screen.getAllByRole("list");
  expect(lists[0].querySelectorAll("li")).toHaveLength(3);
  expect(screen.getByText("Cận chất vải").tagName).toBe("LI");
  expect(lists[1].querySelectorAll("li")).toHaveLength(1);
});

test("an existing project loads its voiceover, product info and length", async () => {
  a.getSettings.mockResolvedValue(VOICE_SETTINGS);
  a.elevenStatus.mockResolvedValue({ hasKey: true });
  a.elevenVoices.mockResolvedValue(VOICES);
  a.getProject.mockResolvedValue(detail([inp("a.mp4")], [], {
    length: "short", voiceover: { enabled: true, voiceId: "v2", voiceName: "Minh" }, productInfo: "Váy đỏ",
  }));
  render(<StoreProvider><NewVideo niche="my-pham" dir="/proj/1" /><Probe /></StoreProvider>);
  expect(await screen.findByLabelText("Thông tin sản phẩm")).toHaveValue("Váy đỏ");
  await waitFor(() => expect(screen.getByLabelText("Giọng đọc")).toHaveValue("v2"));
  expect(screen.getByRole("button", { name: "Ngắn 15–20s" })).toHaveAttribute("aria-pressed", "true");
});

const BUILD = "Dựng video";
const VO_PROJECT = detail([inp("a.mp4")], [], {
  prompt: "ngắn gọn", voiceover: { enabled: true, voiceId: "v2", voiceName: "Minh" }, productInfo: "Váy đỏ",
});
const openExisting = () => render(<StoreProvider><NewVideo niche="my-pham" dir="/proj/1" /><Probe /></StoreProvider>);

test("build while the ElevenLabs key status is still loading does not touch the project's voiceover", async () => {
  a.getSettings.mockResolvedValue(VOICE_SETTINGS);
  const st = deferred<{ hasKey: boolean; remaining?: number }>();
  a.elevenStatus.mockReturnValue(st.promise);
  a.getProject.mockResolvedValue(VO_PROJECT);
  a.setProjectVoiceover.mockResolvedValue(VO_PROJECT);
  openExisting();
  const build = await screen.findByRole("button", { name: BUILD });
  await waitFor(() => expect(build).toBeEnabled());
  await userEvent.click(build);
  await waitFor(() => expect(JSON.parse(screen.getByTestId("r").textContent!)[0]).toEqual({ name: "project", dir: "/proj/1" }));
  expect(a.setProjectVoiceover).not.toHaveBeenCalled();
});

test("an existing project keeps its own voice when Settings has no default voice", async () => {
  a.elevenStatus.mockResolvedValue({ hasKey: true, remaining: 1000 });
  a.elevenVoices.mockResolvedValue(VOICES);
  a.getProject.mockResolvedValue(VO_PROJECT);
  a.setProjectVoiceover.mockResolvedValue(VO_PROJECT);
  openExisting();
  const toggle = await screen.findByRole("checkbox", { name: TOGGLE });
  await waitFor(() => expect(toggle).toBeChecked());
  expect(toggle).toBeEnabled();
  await waitFor(() => expect(screen.getByLabelText("Giọng đọc")).toHaveValue("v2"));
  await userEvent.click(screen.getByRole("button", { name: BUILD }));
  expect(a.setProjectVoiceover).toHaveBeenCalledWith("/proj/1", { enabled: true, voiceId: "v2", voiceName: "Minh" }, "Váy đỏ");
});

test("an existing project keeps its voiceover when the key is gone, until the toggle is turned off", async () => {
  a.elevenStatus.mockResolvedValue({ hasKey: false });
  a.getProject.mockResolvedValue(VO_PROJECT);
  a.setProjectVoiceover.mockResolvedValue(VO_PROJECT);
  openExisting();
  await screen.findByRole("button", { name: "Nhập key ở Cài đặt" });
  const build = screen.getByRole("button", { name: BUILD });
  await waitFor(() => expect(build).toBeEnabled());
  await userEvent.click(build);
  expect(a.setProjectVoiceover).toHaveBeenCalledWith("/proj/1", { enabled: true, voiceId: "v2", voiceName: "Minh" }, "Váy đỏ");
});

test("turning the toggle off on an existing project clears its voiceover", async () => {
  a.elevenStatus.mockResolvedValue({ hasKey: true, remaining: 1000 });
  a.elevenVoices.mockResolvedValue(VOICES);
  a.getProject.mockResolvedValue(VO_PROJECT);
  a.setProjectVoiceover.mockResolvedValue(VO_PROJECT);
  openExisting();
  const toggle = await screen.findByRole("checkbox", { name: TOGGLE });
  await waitFor(() => expect(toggle).toBeChecked());
  await userEvent.click(toggle);
  await userEvent.click(screen.getByRole("button", { name: BUILD }));
  expect(a.setProjectVoiceover).toHaveBeenCalledWith("/proj/1", null, "Váy đỏ");
});
