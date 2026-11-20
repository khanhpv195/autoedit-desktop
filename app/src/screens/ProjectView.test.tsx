import { vi, test, expect, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useState } from "react";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { StoreProvider, useStore } from "../state/store";
import ProjectView from "./ProjectView";

vi.mock("../lib/api");
vi.mock("../lib/engine");
const a = vi.mocked(api);
const e = vi.mocked(engine);

const run1 = { n: 1, final: "/p/1/runs/1/final.mp4", prompt: "p", feedback: null, summary: ["Cắt lặng", "Thêm hook"], needsReview: false, fallback: false };
const detail = (runs: any[]) => ({
  dir: "/p/1", title: "Váy hoa", niche: "thoi-trang", created: "2026-11-20", status: "done" as const, runCount: runs.length,
  clip: "/p/1/clip.mp4", logo: null, music: null, prompt: "làm gọn", scriptCard: null, runs,
});

let emit: (ev: any) => void; let finish: (r: any) => void; const cancel = vi.fn(async () => {});
function fakeRun() {
  e.runEngine.mockImplementation(((_args: string[], onEvent: any) => {
    emit = onEvent;
    return { cancel, result: new Promise((r) => { finish = r; }) };
  }) as any);
}

function Seed({ edit }: { edit?: { dir: string; prompt: string } }) {
  const { dispatch, state } = useStore();
  const [ok, setOk] = useState(false);
  useEffect(() => { if (edit) dispatch({ type: "pendingEdit", pendingEdit: edit }); setOk(true); }, []);
  return ok ? <><ProjectView dir="/p/1" /><div data-testid="r">{JSON.stringify(state.route)}</div></> : null;
}
const mount = (edit?: { dir: string; prompt: string }) => render(<StoreProvider><Seed edit={edit} /></StoreProvider>);

beforeEach(() => {
  vi.clearAllMocks();
  a.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true });
  a.listProjects.mockResolvedValue([]);
  a.fileSrc.mockImplementation((p) => "asset://" + p);
  a.getProject.mockResolvedValue(detail([]));
  fakeRun();
});

test("pendingEdit starts the edit; Building shows steps, feed, preview, cancel", async () => {
  mount({ dir: "/p/1", prompt: "làm gọn" });
  await waitFor(() => expect(e.runEngine).toHaveBeenCalled());
  expect(e.runEngine.mock.calls[0][0]).toEqual(["edit", "--project", "/p/1", "--prompt", "làm gọn"]);
  expect(await screen.findByText("Đang dựng…")).toBeInTheDocument();
  act(() => {
    emit({ type: "step", label: "Chuẩn bị", progress: 0.1 });
    emit({ type: "agent", text: "Cắt đoạn thừa", tool: "set_edl" });
    emit({ type: "preview", path: "/p/1/runs/1/preview.mp4", round: 1 });
    emit({ type: "step", label: "Xuất", progress: 0.95 });
  });
  expect(screen.getByText("Xuất video").closest("li")).toHaveClass("cur");
  expect(screen.getByText("✂️")).toBeInTheDocument();
  expect(screen.getByText("Bản xem nhanh vòng 1")).toBeInTheDocument();
  expect(document.querySelector("video")).toHaveAttribute("src", "asset:///p/1/runs/1/preview.mp4");
  await userEvent.click(screen.getByRole("button", { name: "Hủy" }));
  expect(cancel).toHaveBeenCalled();
});

test("done reloads the project and shows the Result", async () => {
  mount({ dir: "/p/1", prompt: "x" });
  await waitFor(() => expect(e.runEngine).toHaveBeenCalled());
  a.getProject.mockResolvedValue(detail([run1]));
  await act(async () => finish({ code: 0, error: null, last: { type: "done", final: run1.final, summary: [], usage: { turns: 3, fallback: false }, needs_review: false } }));
  expect(await screen.findByText("Cắt lặng")).toBeInTheDocument();
  expect(screen.getByText("Thêm hook")).toBeInTheDocument();
});

test("Result: redo needs feedback, passes --feedback; shows AI feed on open", async () => {
  a.getProject.mockResolvedValue(detail([run1]));
  a.readRunFeed.mockResolvedValue([{ text: "đã cắt", tool: "set_edl" }]);
  mount();
  const redo = await screen.findByRole("button", { name: "Dựng lại" });
  expect(redo).toBeDisabled();
  await userEvent.click(redo);
  expect(e.runEngine).not.toHaveBeenCalled();
  await userEvent.type(screen.getByRole("textbox"), "ngắn hơn");
  await userEvent.click(redo);
  expect(e.runEngine.mock.calls[0][0]).toEqual(["edit", "--project", "/p/1", "--prompt", "làm gọn", "--feedback", "ngắn hơn"]);
  act(() => finish({ code: 1, error: null, last: null }));
  await userEvent.click(await screen.findByText(/Xem quá trình AI/));
  expect(a.readRunFeed).toHaveBeenCalledWith("/p/1", 1);
  expect(await screen.findByText("đã cắt")).toBeInTheDocument();
});

test("RATE_LIMIT error shows retry time", async () => {
  mount({ dir: "/p/1", prompt: "x" });
  await waitFor(() => expect(e.runEngine).toHaveBeenCalled());
  const error = { type: "error", code: "RATE_LIMIT", message: "", retry_at: "2026-11-20T14:30:00+07:00" };
  await act(async () => finish({ code: 2, error, last: error }));
  expect(await screen.findByText("Đã hết lượt Claude")).toBeInTheDocument();
  expect(screen.getByText("Thử lại lúc 14:30")).toBeInTheDocument();
});

test("NO_AUTH opens settings", async () => {
  mount({ dir: "/p/1", prompt: "x" });
  await waitFor(() => expect(e.runEngine).toHaveBeenCalled());
  const error = { type: "error", code: "NO_AUTH", message: "", retry_at: null };
  await act(async () => finish({ code: 1, error, last: error }));
  await userEvent.click(await screen.findByRole("button", { name: "Mở Cài đặt" }));
  expect(screen.getByTestId("r").textContent).toContain("settings");
});
