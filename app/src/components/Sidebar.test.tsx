import { vi, test, expect } from "vitest";
import { render, screen } from "@testing-library/react";
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
  m.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: false });
  render(<StoreProvider><Sidebar /><Probe /></StoreProvider>);
  await screen.findByText(/onboarding/);
  expect(screen.queryByText("AutoEdit")).toBeNull();
});
