import { vi, test, expect, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { StoreProvider, useStore } from "../state/store";
import NewVideo from "./NewVideo";
import type { ChatMessage, ChatPlan, ProjectDetail } from "../lib/types";

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

function Probe() { const { state } = useStore(); return <div data-testid="r">{JSON.stringify([state.route, state.pendingEdit])}</div>; }
const mount = () => render(<StoreProvider><NewVideo niche="my-pham" /><Probe /></StoreProvider>);

const detail = (clips: string[], images: string[], extra: Partial<ProjectDetail> = {}): ProjectDetail => ({
  dir: "/proj/1", title: "a", niche: "my-pham", created: "2026-11-20", status: "new", runCount: 0,
  clips, images, logo: null, music: null, prompt: "", scriptCard: null, runs: [], ...extra,
});
const inp = (n: string) => `/proj/1/input/${n}`;
const START = "Bắt đầu edit";
const PLAN: ChatPlan = {
  summary: ["Thời lượng: ~30s — khách muốn 30s", "Hook: GIÁ CHỈ 199K"], prompt: "Cắt còn 30s, mở bằng câu giá 199K",
  target_seconds: [27, 33], length_source: "customer", length_reason: "khách muốn 30s", hook: "GIÁ CHỈ 199K", cta: "BẤM GIỎ HÀNG",
};
const OPENING: Extract<ChatMessage, { role: "assistant" }> = {
  role: "assistant", text: "Clip có 1 người nói về áo len, khoảng 48s lời.", suggestions: ["Rút còn ~30s"], plan: null, ts: 1,
};
const WITH_PLAN: ChatMessage[] = [OPENING, { role: "user", text: "30s", ts: 2 },
  { role: "assistant", text: "Kế hoạch đây ạ.", suggestions: [], plan: PLAN, ts: 3 }];
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
  a.readChat.mockResolvedValue([]);
  a.renameProject.mockResolvedValue({ dir: "/proj/1", title: "Áo len", niche: "my-pham", created: "2026-11-20", status: "new", runCount: 0 });
  e.chat.mockResolvedValue(OPENING);
});

/** Matches a clip row by its visible order badge + file name, e.g. "2. b.mov". */
const clipRow = (want: string) => (_c: string, el: Element | null) =>
  !!el?.matches(".medialist .row") &&
  `${el.querySelector(".num")?.textContent}. ${el.querySelector(".nm")?.textContent}` === want;

async function addFirst() {
  await userEvent.click(await screen.findByText("Kéo clip và ảnh vào đây"));
  await screen.findByText(clipRow("1. a.mp4"));
}

test("picking a clip creates the project (named after the clip), and the AI opens the chat", async () => {
  mount();
  await addFirst();
  expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4"], [], null, null, CTA, null);
  expect(await screen.findByText(OPENING.text)).toBeInTheDocument();
  expect(e.chat).toHaveBeenCalledWith("/proj/1", "", expect.any(Function), expect.any(Function));
  expect(screen.getByLabelText("Tên video")).toHaveValue("a");
  expect(screen.queryByText("Độ dài video")).toBeNull();
});

test("a name typed before the first clip goes to create; a later change renames on blur", async () => {
  mount();
  await userEvent.type(await screen.findByLabelText("Tên video"), "Áo len");
  await addFirst();
  expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4"], [], null, null, CTA, "Áo len");
  const box = screen.getByLabelText("Tên video");
  await userEvent.type(box, " đỏ");
  await userEvent.tab();
  await waitFor(() => expect(a.renameProject).toHaveBeenCalledWith("/proj/1", "Áo len đỏ"));
  expect(a.listProjects).toHaveBeenCalled();
});

test("Bắt đầu edit saves the plan (prompt + length, no card) and starts the edit", async () => {
  a.readChat.mockResolvedValue(WITH_PLAN);
  mount();
  await addFirst();
  await userEvent.click(await screen.findByRole("button", { name: START }));
  expect(a.updateProject).toHaveBeenCalledWith("/proj/1", { prompt: PLAN.prompt, target_seconds: [27, 33], script_card: null });
  const r = JSON.parse(screen.getByTestId("r").textContent!);
  expect(r[0]).toEqual({ name: "project", dir: "/proj/1" });
  expect(r[1]).toMatchObject({ dir: "/proj/1", prompt: PLAN.prompt });
  expect(e.chat).not.toHaveBeenCalled(); // a saved chat is not re-opened
});

test("opened for an existing project: loads clips, name and the saved chat; no new project", async () => {
  a.getProject.mockResolvedValue(detail([inp("a.mp4"), inp("b.mp4")], [inp("x.png")], { dir: "/proj/9", title: "Áo len" }));
  a.readChat.mockResolvedValue(WITH_PLAN);
  render(<StoreProvider><NewVideo niche="my-pham" dir="/proj/9" /><Probe /></StoreProvider>);
  expect(await screen.findByText("Kế hoạch đây ạ.")).toBeInTheDocument();
  expect(screen.getByText(clipRow("2. b.mp4"))).toBeInTheDocument();
  expect(screen.getByLabelText("Tên video")).toHaveValue("Áo len");
  expect(a.readChat).toHaveBeenCalledWith("/proj/9");
  await userEvent.click(screen.getByRole("button", { name: START }));
  expect(a.createProject).not.toHaveBeenCalled();
  expect(a.updateProject).toHaveBeenCalledWith("/proj/9", expect.objectContaining({ prompt: PLAN.prompt }));
});

function deferred<T>() {
  let resolve!: (v: T) => void, reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
const summary = { dir: "/proj/1", title: "a", niche: "my-pham", created: "2026-11-20", status: "new" as const, runCount: 0 };

test("Bắt đầu edit is disabled while a media sync is pending", async () => {
  a.readChat.mockResolvedValue(WITH_PLAN);
  mount();
  await addFirst();
  const start = await screen.findByRole("button", { name: START });
  await waitFor(() => expect(start).toBeEnabled());
  const slow = deferred<ProjectDetail>();
  a.setProjectMedia.mockReturnValueOnce(slow.promise);
  a.pickMedia.mockResolvedValue(["/v/big.mov"]);
  await userEvent.click(screen.getByText("Thêm file"));
  await waitFor(() => expect(screen.getByRole("button", { name: START })).toBeDisabled());
  await act(async () => { slow.resolve(detail([inp("a.mp4"), inp("big.mov")], [])); });
  await waitFor(() => expect(screen.getByRole("button", { name: START })).toBeEnabled());
});

test("a failed media sync blocks the edit and the chat", async () => {
  a.readChat.mockResolvedValue(WITH_PLAN);
  mount();
  await addFirst();
  await screen.findByRole("button", { name: START });
  a.setProjectMedia.mockRejectedValueOnce({ code: "UNKNOWN", message: "đầy ổ đĩa", retry_at: null });
  a.pickMedia.mockResolvedValue(["/v/big.mov"]);
  await userEvent.click(screen.getByText("Thêm file"));
  await waitFor(() => expect(a.setProjectMedia).toHaveBeenCalled());
  await waitFor(() => expect(screen.getByRole("button", { name: START })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: START }));
  expect(a.updateProject).not.toHaveBeenCalled();
  expect(JSON.parse(screen.getByTestId("r").textContent!)[0]).not.toMatchObject({ name: "project" });
  await userEvent.type(screen.getByLabelText("Tin nhắn cho AI"), "ngắn thôi{Enter}");
  expect(e.chat).not.toHaveBeenCalled();
});

test("multi-drop sorts clips and images, ignores other files, passes images to create", async () => {
  mount();
  await screen.findByText("Kéo clip và ảnh vào đây");
  await waitFor(() => expect(dropHandler).not.toBeNull());
  a.getProject.mockResolvedValue(detail([inp("a.mp4"), inp("b.mov")], [inp("x.png")]));
  // jsdom rects are all zero, so a (0,0) drop counts as inside
  act(() => dropHandler!({ payload: { type: "drop", position: { x: 0, y: 0 }, paths: ["/v/a.mp4", "/v/x.png", "/v/b.mov", "/v/notes.txt"] } }));
  expect(await screen.findByText(clipRow("1. a.mp4"))).toBeInTheDocument();
  expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4", "/v/b.mov"], ["/v/x.png"], null, null, CTA, null);
  expect(await screen.findByText("x.png")).toBeInTheDocument();
  expect(screen.getByText(clipRow("2. b.mov"))).toBeInTheDocument();
});

test("images added first are held; the project is created when the first clip arrives", async () => {
  mount();
  await screen.findByText("Kéo clip và ảnh vào đây");
  await waitFor(() => expect(dropHandler).not.toBeNull());
  act(() => dropHandler!({ payload: { type: "drop", position: { x: 0, y: 0 }, paths: ["/v/x.png"] } }));
  expect(await screen.findByText("x.png")).toBeInTheDocument();
  expect(a.createProject).not.toHaveBeenCalled();
  await userEvent.click(screen.getByText("Thêm file"));
  await waitFor(() => expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4"], ["/v/x.png"], null, null, CTA, null));
});

test("reorder and remove call set_project_media; the last clip cannot be removed", async () => {
  mount();
  await addFirst();
  a.pickMedia.mockResolvedValue(["/v/b.mov", "/v/x.png"]);
  await userEvent.click(screen.getByText("Thêm file"));
  await screen.findByText(clipRow("2. b.mov"));
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

test("clip count is capped at 10", async () => {
  mount();
  await screen.findByText("Kéo clip và ảnh vào đây");
  a.pickMedia.mockResolvedValue(Array.from({ length: 12 }, (_, i) => `/v/c${i}.mp4`));
  a.getProject.mockResolvedValue(detail(Array.from({ length: 10 }, (_, i) => inp(`c${i}.mp4`)), []));
  await userEvent.click(screen.getByText("Kéo clip và ảnh vào đây"));
  await waitFor(() => expect(a.createProject).toHaveBeenCalled());
  expect(a.createProject.mock.calls[0][1]).toHaveLength(10);
});

test("sources added while create is in flight are mapped to input copies, and re-adding is deduped", async () => {
  const create = deferred<typeof summary>();
  a.createProject.mockReturnValueOnce(create.promise);
  mount();
  await addFirst();
  a.pickMedia.mockResolvedValue(["/v/b.mov"]);
  await userEvent.click(screen.getByText("Thêm file"));
  await screen.findByText(clipRow("2. b.mov"));
  await act(async () => { create.resolve(summary); });
  await waitFor(() => expect(a.setProjectMedia).toHaveBeenCalled());
  expect(a.setProjectMedia).toHaveBeenLastCalledWith("/proj/1", [inp("a.mp4"), "/v/b.mov"], []);
  a.pickMedia.mockResolvedValue(["/v/a.mp4"]);
  const before = a.setProjectMedia.mock.calls.length;
  await userEvent.click(screen.getByText("Thêm file"));
  expect(a.setProjectMedia.mock.calls.length).toBe(before);
  expect(screen.queryByText(clipRow("3. a.mp4"))).toBeNull();
});

test("a logo picked while the project is being created is sent after create", async () => {
  const create = deferred<typeof summary>();
  a.createProject.mockReturnValueOnce(create.promise);
  a.pickFile.mockResolvedValue("/v/logo.png");
  a.setProjectAsset.mockResolvedValue(detail([inp("a.mp4")], [], { logo: inp("logo.png") }));
  mount();
  await addFirst();
  await userEvent.click(screen.getByText("Logo"));
  await waitFor(() => expect(a.pickFile).toHaveBeenCalled());
  expect(a.setProjectAsset).not.toHaveBeenCalled();
  await act(async () => { create.resolve(summary); });
  await waitFor(() => expect(a.setProjectAsset).toHaveBeenCalledTimes(1));
  expect(a.setProjectAsset).toHaveBeenCalledWith("/proj/1", "logo", "/v/logo.png");
  expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4"], [], null, null, CTA, null);
});

const VOICE_SETTINGS = { model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true, voiceId: "v1", voiceName: "Lan" };
const VOICES = [
  { id: "v1", name: "Lan", labels: {}, previewUrl: null },
  { id: "v2", name: "Minh", labels: {}, previewUrl: null },
];
const TOGGLE = "Lồng tiếng AI";

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

test("turning voiceover on shows voice + product info, and starting the edit saves them", async () => {
  a.readChat.mockResolvedValue(WITH_PLAN);
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
  await userEvent.click(await screen.findByRole("button", { name: START }));
  expect(a.setProjectVoiceover).toHaveBeenCalledWith("/proj/1", { enabled: true, voiceId: "v2", voiceName: "Minh" }, "Áo lụa 199k");
  expect(JSON.parse(screen.getByTestId("r").textContent!)[0]).toEqual({ name: "project", dir: "/proj/1" });
});

test("with voiceover off, starting the edit clears it", async () => {
  a.readChat.mockResolvedValue(WITH_PLAN);
  a.setProjectVoiceover.mockResolvedValue(detail([inp("a.mp4")], []));
  mount();
  await addFirst();
  await userEvent.click(await screen.findByRole("button", { name: START }));
  expect(a.setProjectVoiceover).toHaveBeenCalledWith("/proj/1", null, "");
});

test("the default logo is pre-filled and can be removed for this video", async () => {
  a.getSettings.mockResolvedValue({ ...VOICE_SETTINGS, defaultLogo: "/data/defaults/logo.png" });
  mount();
  expect(await screen.findByText("logo.png")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Bỏ logo" }));
  expect(screen.queryByText("logo.png")).toBeNull();
  await addFirst();
  expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4"], [], null, null, CTA, null);
});

test("an existing project loads its voiceover and product info", async () => {
  a.getSettings.mockResolvedValue(VOICE_SETTINGS);
  a.elevenStatus.mockResolvedValue({ hasKey: true });
  a.elevenVoices.mockResolvedValue(VOICES);
  a.getProject.mockResolvedValue(detail([inp("a.mp4")], [], {
    voiceover: { enabled: true, voiceId: "v2", voiceName: "Minh" }, productInfo: "Váy đỏ",
  }));
  render(<StoreProvider><NewVideo niche="my-pham" dir="/proj/1" /><Probe /></StoreProvider>);
  expect(await screen.findByLabelText("Thông tin sản phẩm")).toHaveValue("Váy đỏ");
  await waitFor(() => expect(screen.getByLabelText("Giọng đọc")).toHaveValue("v2"));
});

test("the default logo goes to create when kept", async () => {
  a.getSettings.mockResolvedValue({ ...VOICE_SETTINGS, defaultLogo: "/data/defaults/logo.png" });
  mount();
  await screen.findByText("logo.png");
  await addFirst();
  expect(a.createProject).toHaveBeenCalledWith("my-pham", ["/v/a.mp4"], [], "/data/defaults/logo.png", null, CTA, null);
});

const BUILD = START;
const VO_PROJECT = detail([inp("a.mp4")], [], {
  prompt: "ngắn gọn", voiceover: { enabled: true, voiceId: "v2", voiceName: "Minh" }, productInfo: "Váy đỏ",
});
const openExisting = () => { a.readChat.mockResolvedValue(WITH_PLAN); return render(<StoreProvider><NewVideo niche="my-pham" dir="/proj/1" /><Probe /></StoreProvider>); };

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

test("header: Bắt đầu edit stays off until the AI gives a plan; the status pill follows", async () => {
  mount();
  expect(await screen.findByRole("status")).toHaveTextContent("Chờ thêm clip");
  expect(screen.getByRole("button", { name: START })).toBeDisabled();
  await addFirst();
  expect(await screen.findByText(OPENING.text)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Chờ kế hoạch từ AI"));
  expect(screen.getByRole("button", { name: START })).toBeDisabled();
  e.chat.mockResolvedValueOnce({ role: "assistant", text: "Kế hoạch đây ạ.", suggestions: [], plan: PLAN, ts: 3 });
  await userEvent.type(screen.getByLabelText("Tin nhắn cho AI"), "30s{Enter}");
  await waitFor(() => expect(screen.getByRole("button", { name: START })).toBeEnabled());
  expect(screen.getByRole("status")).toHaveTextContent("Sẵn sàng dựng (1 clip)");
  expect(screen.getAllByRole("button", { name: START })).toHaveLength(1); // the plan card points to the header button
});
