import { vi, test, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { StoreProvider } from "../state/store";
import McpSettings, { splitArgs } from "./McpSettings";

vi.mock("../lib/api");
vi.mock("../lib/engine");
const a = vi.mocked(api);
const e = vi.mocked(engine);

const shop: any = { name: "shop", enabled: true, transport: "stdio", command: "npx", args: ["-y", "srv"], envKeys: ["TOKEN"] };

beforeEach(() => {
  vi.clearAllMocks();
  a.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: false });
  a.mcpList.mockResolvedValue([]);
  a.mcpSave.mockResolvedValue(null);
  a.mcpDelete.mockResolvedValue(null);
});
const mount = () => render(<StoreProvider><McpSettings /></StoreProvider>);

test("always shows the trust warning", async () => {
  mount();
  expect(await screen.findByText(/Chỉ thêm server bạn tin tưởng/)).toBeInTheDocument();
});

test("adding a stdio server saves envKeys and the secret value separately", async () => {
  mount();
  await userEvent.click(await screen.findByRole("button", { name: /Thêm MCP server/ }));
  await userEvent.type(screen.getByLabelText("Tên MCP"), "kho-anh");
  await userEvent.type(screen.getByLabelText("Lệnh"), "npx");
  await userEvent.type(screen.getByLabelText("Tham số"), '-y @shop/mcp "hai từ"');
  await userEvent.click(screen.getByRole("button", { name: /Thêm biến môi trường/ }));
  await userEvent.type(screen.getByLabelText("Tên biến môi trường 1"), "API_KEY");
  await userEvent.type(screen.getByLabelText("Giá trị biến môi trường 1"), "s3cret");
  await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(a.mcpSave).toHaveBeenCalledWith(
    { name: "kho-anh", enabled: true, transport: "stdio", command: "npx", args: ["-y", "@shop/mcp", "hai từ"], envKeys: ["API_KEY"] },
    { API_KEY: "s3cret" },
  );
});

test("an invalid name shows an error and does not save", async () => {
  mount();
  await userEvent.click(await screen.findByRole("button", { name: /Thêm MCP server/ }));
  await userEvent.type(screen.getByLabelText("Tên MCP"), "Bad Name");
  await userEvent.type(screen.getByLabelText("Lệnh"), "npx");
  await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(await screen.findByText(/Tên chỉ gồm chữ thường/)).toBeInTheDocument();
  expect(a.mcpSave).not.toHaveBeenCalled();
});

test("editing without typing a secret sends empty secrets (keeps the stored value)", async () => {
  a.mcpList.mockResolvedValue([shop]);
  mount();
  await userEvent.click(await screen.findByRole("button", { name: "Sửa shop" }));
  expect(screen.getByPlaceholderText("•••• đã lưu")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(a.mcpSave).toHaveBeenCalledWith(expect.objectContaining({ name: "shop", envKeys: ["TOKEN"], args: ["-y", "srv"] }), {});
});

test("http server needs an http(s) url and stores header keys", async () => {
  mount();
  await userEvent.click(await screen.findByRole("button", { name: /Thêm MCP server/ }));
  await userEvent.click(screen.getByRole("button", { name: "URL (HTTP)" }));
  await userEvent.type(screen.getByLabelText("Tên MCP"), "web");
  await userEvent.type(screen.getByLabelText("URL"), "ftp://x");
  await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(await screen.findByText(/http:\/\/ hoặc https:\/\//)).toBeInTheDocument();
  await userEvent.clear(screen.getByLabelText("URL"));
  await userEvent.type(screen.getByLabelText("URL"), "https://x.io/mcp");
  await userEvent.click(screen.getByRole("button", { name: /Thêm header/ }));
  await userEvent.type(screen.getByLabelText("Tên header 1"), "Authorization");
  await userEvent.type(screen.getByLabelText("Giá trị header 1"), "Bearer z");
  await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(a.mcpSave).toHaveBeenCalledWith(
    { name: "web", enabled: true, transport: "http", url: "https://x.io/mcp", headerKeys: ["Authorization"] },
    { Authorization: "Bearer z" },
  );
});

test("Kiểm tra lists the tools", async () => {
  a.mcpList.mockResolvedValue([shop]);
  e.mcpCheck.mockResolvedValue([{ name: "price", description: "Giá theo SKU" }]);
  mount();
  await userEvent.click(await screen.findByRole("button", { name: "Kiểm tra shop" }));
  expect(e.mcpCheck).toHaveBeenCalledWith("shop");
  expect(await screen.findByText("price")).toBeInTheDocument();
  expect(screen.getByText(/Giá theo SKU/)).toBeInTheDocument();
});

test("Kiểm tra failure shows the message", async () => {
  a.mcpList.mockResolvedValue([shop]);
  e.mcpCheck.mockRejectedValue({ code: "AGENT_FAILED", message: "Không kết nối được MCP shop: hết giờ", retry_at: null });
  mount();
  await userEvent.click(await screen.findByRole("button", { name: "Kiểm tra shop" }));
  expect(await screen.findByText(/hết giờ/)).toBeInTheDocument();
});

test("toggle saves with empty secrets; delete asks for confirmation first", async () => {
  a.mcpList.mockResolvedValue([shop]);
  mount();
  await userEvent.click(await screen.findByRole("switch", { name: "Bật shop" }));
  expect(a.mcpSave).toHaveBeenCalledWith({ ...shop, enabled: false }, {});
  const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
  await userEvent.click(screen.getByRole("button", { name: "Xóa shop" }));
  expect(a.mcpDelete).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Xóa shop" }));
  await waitFor(() => expect(a.mcpDelete).toHaveBeenCalledWith("shop"));
  confirm.mockRestore();
});

test("the add button is disabled at 10 servers", async () => {
  a.mcpList.mockResolvedValue(Array.from({ length: 10 }, (_, i) => ({ ...shop, name: `s${i}` })));
  mount();
  await screen.findByText("s9");
  expect(screen.getByRole("button", { name: /Thêm MCP server/ })).toBeDisabled();
});

test("splitArgs keeps quoted strings together", () => {
  expect(splitArgs(`-y "a b" 'c d' e`)).toEqual(["-y", "a b", "c d", "e"]);
  expect(splitArgs("")).toEqual([]);
});
