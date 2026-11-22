import { vi, test, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { StoreProvider, useStore } from "../state/store";
import type { ProjectSummary } from "../lib/types";
import Library, { resetBackfillForTests } from "./Library";

vi.mock("../lib/api");
vi.mock("../lib/engine");
const m = vi.mocked(api);
const e = vi.mocked(engine);

function Probe() {
  const { state } = useStore();
  return <div data-testid="route">{JSON.stringify(state.route)}</div>;
}

const P = (dir: string, title: string, extra: Partial<ProjectSummary> = {}) =>
  ({ dir, title, niche: "thoi-trang", created: "2026-11-20", status: "done", runCount: 1, thumb: `${dir}/runs/1/thumb.jpg`, ...extra });

function boot(projects: unknown[]) {
  m.licenseStatus.mockResolvedValue({ licensed: true, name: "Test" });
  m.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/root", lastNiche: null, onboarded: true });
  m.listProjects.mockResolvedValue(projects as never);
  m.fileSrc.mockImplementation((p: string) => "asset://" + p);
  e.backfillThumbs.mockResolvedValue();
}

beforeEach(() => { vi.clearAllMocks(); resetBackfillForTests(); });

test("grid shows every project with its thumbnail and opens one on click", async () => {
  boot([P("/a", "Váy hoa"), P("/b", "Son đỏ", { niche: "my-pham", thumb: null, runCount: 0, status: "new" })]);
  render(<StoreProvider><Library /><Probe /></StoreProvider>);
  expect(await screen.findByText("Váy hoa")).toBeInTheDocument();
  expect(screen.getByText(/2 video/)).toBeInTheDocument();
  expect(screen.getByAltText("Váy hoa")).toHaveAttribute("src", "asset:///a/runs/1/thumb.jpg");
  expect(screen.queryByAltText("Son đỏ")).toBeNull();
  await userEvent.click(screen.getByText("Son đỏ"));
  expect(screen.getByTestId("route").textContent).toContain('"/b"');
});

test("search without diacritics, then clear filters from the empty state", async () => {
  boot([P("/a", "Váy hoa"), P("/b", "Son đỏ")]);
  render(<StoreProvider><Library /></StoreProvider>);
  await screen.findByText("Váy hoa");
  await userEvent.type(screen.getByPlaceholderText("Tìm theo tên…"), "son do");
  expect(screen.queryByText("Váy hoa")).toBeNull();
  expect(screen.getByText("Son đỏ")).toBeInTheDocument();
  await userEvent.type(screen.getByPlaceholderText("Tìm theo tên…"), "xyz");
  expect(screen.getByText("Không có video khớp bộ lọc")).toBeInTheDocument();
  await userEvent.click(screen.getByText("Xoá bộ lọc"));
  expect(screen.getByText("Váy hoa")).toBeInTheDocument();
});

test("status filter", async () => {
  boot([P("/a", "Váy hoa"), P("/b", "Son đỏ", { status: "needs_review" })]);
  render(<StoreProvider><Library /></StoreProvider>);
  await screen.findByText("Váy hoa");
  await userEvent.selectOptions(screen.getByLabelText("Trạng thái"), "needs_review");
  expect(screen.queryByText("Váy hoa")).toBeNull();
  expect(screen.getByText("Son đỏ")).toBeInTheDocument();
});

test("empty library offers 'Video mới'", async () => {
  boot([]);
  render(<StoreProvider><Library /><Probe /></StoreProvider>);
  expect(await screen.findByText("Chưa có video nào")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Video mới/ }));
  expect(screen.getByTestId("route").textContent).toContain('"niche"');
});

test("backfills missing thumbnails once per session", async () => {
  boot([P("/a", "Váy hoa", { thumb: null })]);
  const { unmount } = render(<StoreProvider><Library /></StoreProvider>);
  await waitFor(() => expect(e.backfillThumbs).toHaveBeenCalledTimes(1));
  expect(e.backfillThumbs.mock.calls[0][0]).toBe("/root");
  unmount();
  render(<StoreProvider><Library /></StoreProvider>);
  await screen.findByText("Váy hoa");
  expect(e.backfillThumbs).toHaveBeenCalledTimes(1);
});

test("no backfill when every built project has a thumbnail", async () => {
  boot([P("/a", "Váy hoa"), P("/b", "Mới", { thumb: null, runCount: 0, status: "new" })]);
  render(<StoreProvider><Library /></StoreProvider>);
  await screen.findByText("Váy hoa");
  expect(e.backfillThumbs).not.toHaveBeenCalled();
});
