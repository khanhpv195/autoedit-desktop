import { vi, test, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import { StoreProvider, useStore } from "../state/store";
import NichePicker from "./NichePicker";

vi.mock("../lib/api");
const m = vi.mocked(api);
const base = { model: "m", projectsRoot: "/p", lastNiche: "my-pham", onboarded: true };

function Probe() { const { state } = useStore(); return <div data-testid="r">{JSON.stringify(state.route)}</div>; }
beforeEach(() => {
  vi.clearAllMocks();
  m.getSettings.mockResolvedValue(base);
  m.listProjects.mockResolvedValue([]);
  m.saveSettings.mockResolvedValue(null);
});

test("marks last niche and saves the picked one", async () => {
  render(<StoreProvider><NichePicker /><Probe /></StoreProvider>);
  expect(await screen.findByText("Hôm nay dựng video gì?")).toBeInTheDocument();
  await screen.findByText("Lần trước");
  expect(screen.getByText("Mỹ phẩm").closest(".catcard")).toContainElement(screen.getByText("Lần trước"));
  await userEvent.click(screen.getByText("Đồ ăn"));
  expect(m.saveSettings).toHaveBeenCalledWith({ ...base, lastNiche: "do-an" });
  expect(screen.getByTestId("r").textContent).toContain('"niche":"do-an"');
});
