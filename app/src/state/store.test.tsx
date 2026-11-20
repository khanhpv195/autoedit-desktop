import { vi, test, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import * as api from "../lib/api";
import { StoreProvider, useStore } from "./store";

vi.mock("../lib/api");
const m = vi.mocked(api);

function Probe() {
  const { state } = useStore();
  return <div>route:{state.route.name} n:{state.projects.length}</div>;
}
const settings = { model: "claude-opus-5-5", projectsRoot: "/p", lastNiche: null };

beforeEach(() => vi.clearAllMocks());

test("not onboarded -> onboarding route", async () => {
  m.getSettings.mockResolvedValue({ ...settings, onboarded: false });
  render(<StoreProvider><Probe /></StoreProvider>);
  expect(await screen.findByText(/route:onboarding/)).toBeInTheDocument();
  expect(m.listProjects).not.toHaveBeenCalled();
});
test("onboarded -> loads projects, route niche", async () => {
  m.getSettings.mockResolvedValue({ ...settings, onboarded: true });
  m.listProjects.mockResolvedValue([{ dir: "/a", title: "A", niche: "chung", created: "2026-11-20", status: "new", runCount: 0 }]);
  render(<StoreProvider><Probe /></StoreProvider>);
  expect(await screen.findByText(/route:niche n:1/)).toBeInTheDocument();
  expect(m.listProjects).toHaveBeenCalled();
});
