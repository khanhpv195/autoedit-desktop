import { vi, test, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import * as api from "./lib/api";
import App from "./App";

vi.mock("./lib/api");
vi.mock("./lib/engine");

test("hiện sidebar khi đã onboard", async () => {
  vi.mocked(api.getSettings).mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true });
  vi.mocked(api.listProjects).mockResolvedValue([]);
  render(<App />);
  expect(await screen.findByText("AutoEdit")).toBeInTheDocument();
});
