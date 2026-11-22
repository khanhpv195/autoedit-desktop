import { vi, test, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import { StoreProvider, useStore } from "../state/store";
import Sidebar from "./Sidebar";

vi.mock("../lib/api");
const m = vi.mocked(api);

function Probe() {
  const { state } = useStore();
  return <div data-testid="route">{JSON.stringify(state.route)}</div>;
}

test("lists projects, counts them and navigates on click", async () => {
  m.licenseStatus.mockResolvedValue({ licensed: true, name: "Test" });
  m.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true });
  m.listProjects.mockResolvedValue([
    { dir: "/a", title: "Váy hoa", niche: "thoi-trang", created: "2026-11-20", status: "done", runCount: 1 },
    { dir: "/b", title: "Son đỏ", niche: "my-pham", created: "2026-11-19", status: "needs_review", runCount: 1 },
  ]);
  render(<StoreProvider><Sidebar /><Probe /></StoreProvider>);
  expect(await screen.findByText("Váy hoa")).toBeInTheDocument();
  expect(screen.getByText("Son đỏ")).toBeInTheDocument();
  expect(screen.getByText("2 video")).toBeInTheDocument();
  expect(screen.getByText(/Lịch đăng/).closest(".sn")).toHaveAttribute("aria-disabled", "true");
  await userEvent.click(screen.getByText("Son đỏ"));
  expect(screen.getByTestId("route").textContent).toContain('"project"');
  expect(screen.getByTestId("route").textContent).toContain("/b");
});

test("hidden during onboarding", async () => {
  m.licenseStatus.mockResolvedValue({ licensed: true, name: "Test" });
  m.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: false });
  render(<StoreProvider><Sidebar /><Probe /></StoreProvider>);
  await screen.findByText(/onboarding/);
  expect(screen.queryByText("AutoEdit")).toBeNull();
});

test("shows a building marker for a project with a running job", async () => {
  m.licenseStatus.mockResolvedValue({ licensed: true, name: "Test" });
  m.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true });
  m.listProjects.mockResolvedValue([
    { dir: "/a", title: "Váy hoa", niche: "thoi-trang", created: "2026-11-20", status: "done", runCount: 1 },
  ]);
  function Start() {
    const { dispatch } = useStore();
    return <button onClick={() => dispatch({ type: "buildStart", dir: "/a", last: { prompt: "x" } })}>go</button>;
  }
  const { container } = render(<StoreProvider><Sidebar /><Start /></StoreProvider>);
  await screen.findByText("Váy hoa");
  await userEvent.click(screen.getByText("go"));
  expect(screen.getByText("đang dựng…")).toBeInTheDocument();
  expect(container.querySelector("i.st")).toHaveAttribute("data-status", "building");
});

const boot = (projects: Parameters<typeof m.listProjects.mockResolvedValue>[0]) => {
  m.licenseStatus.mockResolvedValue({ licensed: true, name: "Test" });
  m.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true });
  m.listProjects.mockResolvedValue(projects);
};
const VAY = { dir: "/a", title: "Váy hoa", niche: "thoi-trang", created: "2026-11-20", status: "done" as const, runCount: 2, scheduledPosts: 0 };

function GoTo({ dir }: { dir: string }) {
  const { go } = useStore();
  return <button onClick={() => go({ name: "project", dir })}>open</button>;
}

test("⋯ → Đổi tên renames inline with Enter and refreshes the list", async () => {
  boot([VAY]);
  m.renameProject.mockResolvedValue({ ...VAY, title: "Váy hoa đỏ" });
  render(<StoreProvider><Sidebar /><Probe /></StoreProvider>);
  await screen.findByText("Váy hoa");
  await userEvent.click(screen.getByRole("button", { name: "Tuỳ chọn Váy hoa" }));
  await userEvent.click(screen.getByRole("menuitem", { name: "Đổi tên" }));
  const input = screen.getByLabelText("Tên video");
  expect(input).toHaveValue("Váy hoa");
  m.listProjects.mockResolvedValue([{ ...VAY, title: "Váy hoa đỏ" }]);
  await userEvent.clear(input);
  await userEvent.type(input, "Váy hoa đỏ{Enter}");
  expect(m.renameProject).toHaveBeenCalledWith("/a", "Váy hoa đỏ");
  expect(await screen.findByText("Váy hoa đỏ")).toBeInTheDocument();
  expect(screen.getByTestId("route").textContent).not.toContain('"project"'); // editing does not open the project
});

test("Esc cancels a rename without saving", async () => {
  boot([VAY]);
  render(<StoreProvider><Sidebar /></StoreProvider>);
  await screen.findByText("Váy hoa");
  await userEvent.click(screen.getByRole("button", { name: "Tuỳ chọn Váy hoa" }));
  await userEvent.click(screen.getByRole("menuitem", { name: "Đổi tên" }));
  await userEvent.type(screen.getByLabelText("Tên video"), "xyz{Escape}");
  expect(m.renameProject).not.toHaveBeenCalled();
  expect(screen.getByText("Váy hoa")).toBeInTheDocument();
});

test("Xoá asks first; Huỷ keeps the project", async () => {
  boot([VAY]);
  render(<StoreProvider><Sidebar /></StoreProvider>);
  await screen.findByText("Váy hoa");
  await userEvent.click(screen.getByRole("button", { name: "Tuỳ chọn Váy hoa" }));
  await userEvent.click(screen.getByRole("menuitem", { name: "Xoá…" }));
  const dlg = screen.getByRole("dialog", { name: "Xoá video" });
  expect(dlg).toHaveTextContent("2 video đã xuất");
  expect(dlg).toHaveTextContent("File gốc của bạn");
  await userEvent.click(screen.getByRole("button", { name: "Huỷ" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(m.deleteProject).not.toHaveBeenCalled();
});

test("confirming deletes the project, refreshes the list and leaves its open screen", async () => {
  boot([VAY, { ...VAY, dir: "/b", title: "Son đỏ" }]);
  m.deleteProject.mockResolvedValue(null);
  render(<StoreProvider><Sidebar /><GoTo dir="/a" /><Probe /></StoreProvider>);
  await screen.findByText("Váy hoa");
  await userEvent.click(screen.getByText("open"));
  expect(screen.getByTestId("route").textContent).toContain("/a");
  await userEvent.click(screen.getByRole("button", { name: "Tuỳ chọn Váy hoa" }));
  await userEvent.click(screen.getByRole("menuitem", { name: "Xoá…" }));
  m.listProjects.mockResolvedValue([{ ...VAY, dir: "/b", title: "Son đỏ" }]);
  await userEvent.click(screen.getByRole("button", { name: "Xoá" }));
  expect(m.deleteProject).toHaveBeenCalledWith("/a");
  await waitFor(() => expect(screen.queryByText("Váy hoa")).toBeNull());
  expect(screen.getByText("Son đỏ")).toBeInTheDocument();
  expect(JSON.parse(screen.getByTestId("route").textContent!)).toEqual({ name: "niche" });
});

test("the confirm dialog warns about posts still scheduled on bundle.social", async () => {
  boot([{ ...VAY, scheduledPosts: 2 }]);
  render(<StoreProvider><Sidebar /></StoreProvider>);
  await screen.findByText("Váy hoa");
  await userEvent.click(screen.getByRole("button", { name: "Tuỳ chọn Váy hoa" }));
  await userEvent.click(screen.getByRole("menuitem", { name: "Xoá…" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("2 bài đã hẹn giờ trên bundle.social vẫn sẽ được đăng");
});

test("a failed delete keeps the project in the list", async () => {
  boot([VAY]);
  m.deleteProject.mockRejectedValue("Video này đang được AI xử lý, hãy dừng hoặc chờ xong rồi xoá");
  render(<StoreProvider><Sidebar /></StoreProvider>);
  await screen.findByText("Váy hoa");
  await userEvent.click(screen.getByRole("button", { name: "Tuỳ chọn Váy hoa" }));
  await userEvent.click(screen.getByRole("menuitem", { name: "Xoá…" }));
  await userEvent.click(screen.getByRole("button", { name: "Xoá" }));
  await waitFor(() => expect(m.deleteProject).toHaveBeenCalled());
  expect(screen.getByText("Váy hoa")).toBeInTheDocument();
});
