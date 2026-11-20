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
