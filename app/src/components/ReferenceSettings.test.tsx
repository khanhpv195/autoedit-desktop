import { vi, test, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as engine from "../lib/engine";
import ReferenceSettings from "./ReferenceSettings";

vi.mock("../lib/engine");
const e = vi.mocked(engine);
const ref = (id: string, name: string) => ({ id, name, niche: "thoi-trang", project: "/p/" + id, run: 1, saved_at: 1 });

beforeEach(() => { vi.clearAllMocks(); });

test("lists the saved video mẫu and removes one", async () => {
  e.listReferences.mockResolvedValue([ref("a-run1", "Clip-chuan"), ref("b-run1", "Váy hoa")]);
  e.deleteReference.mockResolvedValue([ref("b-run1", "Váy hoa")]);
  render(<ReferenceSettings />);
  expect(await screen.findByText("Clip-chuan · lần 1 · Thời trang")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Bỏ mẫu Clip-chuan" }));
  expect(e.deleteReference).toHaveBeenCalledWith("a-run1");
  expect(await screen.findByText("Váy hoa · lần 1 · Thời trang")).toBeInTheDocument();
  expect(screen.queryByText(/Clip-chuan ·/)).toBeNull();
});

test("empty list and a read error", async () => {
  e.listReferences.mockRejectedValue(new Error("Không đọc được video mẫu"));
  render(<ReferenceSettings />);
  expect(await screen.findByText("Chưa lưu video mẫu nào.")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Không đọc được video mẫu");
});
