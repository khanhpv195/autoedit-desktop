import { test, expect } from "vitest";
import { describeError } from "./errors";

test("RATE_LIMIT shows local retry time", () => {
  const d = describeError({ code: "RATE_LIMIT", message: "", retry_at: "2026-11-20T14:30:00+07:00" });
  expect(d.title).toBe("Đã hết lượt Claude");
  expect(d.detail).toBe("Thử lại lúc 14:30");
  expect(d.action).toBe("retry");
});
test("RATE_LIMIT without time", () => {
  expect(describeError({ code: "RATE_LIMIT", message: "", retry_at: null }).detail).toBe("Thử lại sau ít phút");
});
test("NO_AUTH goes to settings, SETUP_REQUIRED to setup, BAD_INPUT none", () => {
  expect(describeError({ code: "NO_AUTH", message: "", retry_at: null }).action).toBe("settings");
  expect(describeError({ code: "SETUP_REQUIRED", message: "", retry_at: null }).action).toBe("setup");
  expect(describeError({ code: "BAD_INPUT", message: "hỏng", retry_at: null })).toMatchObject({ detail: "hỏng", action: "none" });
});
test("unknown code retries", () => {
  expect(describeError({ code: "WAT", message: "x", retry_at: null }).action).toBe("retry");
});
test("SOCIAL_* codes", () => {
  expect(describeError({ code: "SOCIAL_AUTH", message: "", retry_at: null })).toMatchObject({ title: "Key bundle.social không dùng được", action: "settings" });
  expect(describeError({ code: "SOCIAL_LIMIT", message: "", retry_at: null })).toMatchObject({ title: "Hết lượt đăng của gói bundle.social", action: "none" });
  expect(describeError({ code: "SOCIAL_FAILED", message: "boom", retry_at: null })).toMatchObject({ title: "Đăng bài lỗi", detail: "boom", action: "retry" });
});

test("social context: BAD_INPUT is 'Chưa đăng được' with the engine message; caption context has its own title", () => {
  expect(describeError({ code: "BAD_INPUT", message: "Giờ đăng đã qua", retry_at: null }, "social"))
    .toMatchObject({ title: "Chưa đăng được", detail: "Giờ đăng đã qua", action: "none" });
  expect(describeError({ code: "AGENT_FAILED", message: "hỏng", retry_at: null }, "caption").title).toBe("Chưa viết được caption");
  expect(describeError({ code: "BAD_INPUT", message: "dài quá", retry_at: null }, "caption")).toMatchObject({ title: "Chưa viết được caption", detail: "dài quá" });
  // specific codes keep their own wording, and no context keeps the old titles
  expect(describeError({ code: "RATE_LIMIT", message: "", retry_at: null }, "caption").title).toBe("Đã hết lượt Claude");
  expect(describeError({ code: "BAD_INPUT", message: "x", retry_at: null }).title).toBe("File không dùng được");
});
