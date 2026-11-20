import { vi, test, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import UpdateBanner from "./UpdateBanner";

vi.mock("@tauri-apps/plugin-updater", () => ({ check: vi.fn() }));
vi.mock("@tauri-apps/plugin-process", () => ({ relaunch: vi.fn() }));

beforeEach(() => vi.clearAllMocks());

test("shows nothing when there is no update", async () => {
  vi.mocked(check).mockResolvedValue(null);
  const { container } = render(<UpdateBanner />);
  await waitFor(() => expect(check).toHaveBeenCalled());
  expect(container).toBeEmptyDOMElement();
});

test("shows the new version and installs then relaunches on click", async () => {
  const downloadAndInstall = vi.fn().mockResolvedValue(undefined);
  vi.mocked(check).mockResolvedValue({ version: "0.2.0", downloadAndInstall } as never);
  render(<UpdateBanner />);
  expect(await screen.findByText(/Có bản mới 0\.2\.0/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Cập nhật" }));
  await waitFor(() => expect(relaunch).toHaveBeenCalled());
  expect(downloadAndInstall).toHaveBeenCalled();
});

test("stays silent when check throws", async () => {
  vi.mocked(check).mockRejectedValue(new Error("endpoint"));
  const { container } = render(<UpdateBanner />);
  await waitFor(() => expect(check).toHaveBeenCalled());
  expect(container).toBeEmptyDOMElement();
});
