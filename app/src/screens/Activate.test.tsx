import { vi, test, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import Activate from "./Activate";

vi.mock("../lib/api");
const a = vi.mocked(api);
beforeEach(() => vi.clearAllMocks());

const KEY = "AE-AAAA-BBBB-CCCC-DDDD";

test("shows the title, a key input and a disabled button while empty", () => {
  render(<Activate onDone={() => {}} />);
  expect(screen.getByText("Kích hoạt AutoEdit")).toBeInTheDocument();
  expect(screen.getByPlaceholderText("AE-XXXX-XXXX-XXXX-XXXX")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Kích hoạt" })).toBeDisabled();
});

test("activates with the typed key and calls onDone", async () => {
  a.licenseActivate.mockResolvedValue({ licensed: true, name: "Shop A" });
  const onDone = vi.fn();
  render(<Activate onDone={onDone} />);
  await userEvent.type(screen.getByPlaceholderText("AE-XXXX-XXXX-XXXX-XXXX"), KEY);
  await userEvent.click(screen.getByRole("button", { name: "Kích hoạt" }));
  expect(a.licenseActivate).toHaveBeenCalledWith(KEY);
  expect(onDone).toHaveBeenCalled();
});

test("shows the used-elsewhere message and does not continue", async () => {
  a.licenseActivate.mockRejectedValue("LICENSE_USED");
  const onDone = vi.fn();
  render(<Activate onDone={onDone} />);
  await userEvent.type(screen.getByPlaceholderText("AE-XXXX-XXXX-XXXX-XXXX"), KEY);
  await userEvent.click(screen.getByRole("button", { name: "Kích hoạt" }));
  expect(await screen.findByText("Key đã được kích hoạt trên máy khác. Liên hệ người bán để được hỗ trợ.")).toBeInTheDocument();
  expect(onDone).not.toHaveBeenCalled();
});

test("maps invalid, offline and unknown errors", async () => {
  a.licenseActivate.mockRejectedValueOnce("LICENSE_INVALID").mockRejectedValueOnce("LICENSE_OFFLINE");
  render(<Activate onDone={() => {}} />);
  await userEvent.type(screen.getByPlaceholderText("AE-XXXX-XXXX-XXXX-XXXX"), KEY);
  await userEvent.click(screen.getByRole("button", { name: "Kích hoạt" }));
  expect(await screen.findByText("Key không đúng")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Kích hoạt" }));
  expect(await screen.findByText(/Không kết nối được máy chủ kích hoạt/)).toBeInTheDocument();
});

test("a revoked reason is shown before any click", () => {
  render(<Activate reason="LICENSE_REVOKED" onDone={() => {}} />);
  expect(screen.getByText("Key đã bị thu hồi")).toBeInTheDocument();
});

test("while pending the button says Đang kích hoạt… and is disabled", async () => {
  a.licenseActivate.mockReturnValue(new Promise(() => {}));
  render(<Activate onDone={() => {}} />);
  await userEvent.type(screen.getByPlaceholderText("AE-XXXX-XXXX-XXXX-XXXX"), KEY);
  await userEvent.click(screen.getByRole("button", { name: "Kích hoạt" }));
  const b = await screen.findByRole("button", { name: "Đang kích hoạt…" });
  expect(b).toBeDisabled();
});

test("sends the normalised key", async () => {
  a.licenseActivate.mockResolvedValue({ licensed: true, name: "Shop A" });
  render(<Activate onDone={() => {}} />);
  await userEvent.type(screen.getByPlaceholderText("AE-XXXX-XXXX-XXXX-XXXX"), " ae7kq2m9xdooilzzzz ");
  await userEvent.click(screen.getByRole("button", { name: "Kích hoạt" }));
  expect(a.licenseActivate).toHaveBeenCalledWith("AE-7KQ2-M9XD-0011-ZZZZ");
});
