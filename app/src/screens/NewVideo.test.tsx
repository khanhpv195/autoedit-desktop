import { vi, test, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { StoreProvider, useStore } from "../state/store";
import NewVideo from "./NewVideo";

vi.mock("../lib/api");
vi.mock("../lib/engine");
const a = vi.mocked(api);
const e = vi.mocked(engine);
const cards = [1, 2, 3].map((i) => ({ title: `Ý ${i}`, hook: `Hook ${i}`, outline: `Outline ${i}`, prompt: `Prompt ${i}` }));

function Probe() { const { state } = useStore(); return <div data-testid="r">{JSON.stringify([state.route, state.pendingEdit])}</div>; }
const mount = () => render(<StoreProvider><NewVideo niche="my-pham" /><Probe /></StoreProvider>);

beforeEach(() => {
  vi.clearAllMocks();
  a.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true });
  a.listProjects.mockResolvedValue([]);
  a.pickFile.mockResolvedValue("/v/a.mp4");
  a.createProject.mockResolvedValue({ dir: "/proj/1", title: "a", niche: "my-pham", created: "2026-11-20", status: "new", runCount: 0 });
  a.updateProject.mockResolvedValue(null);
});

test("pick clip -> create + analyze -> pick card fills prompt -> more -> build", async () => {
  e.analyze.mockResolvedValue(cards);
  mount();
  await userEvent.click(await screen.findByText("Kéo clip vào đây"));
  expect(a.createProject).toHaveBeenCalledWith("my-pham", "/v/a.mp4", null, null);
  expect(e.analyze).toHaveBeenCalledWith("/proj/1", [], expect.any(Function));
  expect(await screen.findByText("Ý 2")).toBeInTheDocument();
  expect(screen.getByText("Ý 3")).toBeInTheDocument();
  await userEvent.click(screen.getByText("Ý 2"));
  expect(screen.getByRole("textbox")).toHaveValue("Prompt 2");
  expect(a.updateProject).toHaveBeenCalledWith("/proj/1", { script_card: cards[1] });

  await userEvent.click(screen.getByText("↻ Gợi ý khác"));
  expect(e.analyze).toHaveBeenLastCalledWith("/proj/1", ["Ý 1", "Ý 2", "Ý 3"], expect.any(Function));

});

test("build dispatches route project with pendingEdit", async () => {
  e.analyze.mockResolvedValue(cards);
  mount();
  await userEvent.click(await screen.findByText("Kéo clip vào đây"));
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
  await userEvent.click(await screen.findByText("Kéo clip vào đây"));
  expect(await screen.findByText("Đã hết lượt Claude")).toBeInTheDocument();
  const btn = screen.getByRole("button", { name: "Dựng video" });
  expect(btn).toBeDisabled();
  await userEvent.type(screen.getByRole("textbox"), "ngắn thôi");
  expect(btn).toBeEnabled();
});
