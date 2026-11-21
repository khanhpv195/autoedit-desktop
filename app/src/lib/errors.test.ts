import { test, expect } from "vitest";
import { describeError, toEngineError } from "./errors";

test("ElevenLabs settings codes and VOICE_* engine codes", () => {
  const d = (code: string, message = "") => describeError({ code, message, retry_at: null });
  expect(d("ELEVEN_KEY_INVALID")).toMatchObject({ title: "Key ElevenLabs không đúng", action: "settings" });
  expect(d("ELEVEN_OFFLINE")).toMatchObject({ title: "Không kết nối được ElevenLabs", action: "retry" });
  expect(d("ELEVEN_FAILED")).toMatchObject({ title: "ElevenLabs đang lỗi hoặc bận, thử lại sau", action: "retry" });
  expect(d("VOICE_AUTH")).toMatchObject({ title: "Key ElevenLabs không đúng", action: "settings" });
  expect(d("VOICE_QUOTA")).toMatchObject({ title: "Tài khoản ElevenLabs hết ký tự", action: "none" });
  expect(d("VOICE_MISSING").title).toBe("Giọng đọc không còn trong tài khoản ElevenLabs, chọn giọng khác trong Cài đặt");
  expect(d("VOICE_MISSING").action).toBe("settings");
  expect(d("VOICE_LIMIT")).toMatchObject({ title: "ElevenLabs đang bận, thử lại sau", action: "retry" });
  expect(d("VOICE_FAILED", "boom")).toMatchObject({ title: "Lồng tiếng bị lỗi", detail: "boom", action: "retry" });
});

test("a rejected command carrying a bare known code becomes that code", () => {
  expect(toEngineError("ELEVEN_KEY_INVALID")).toMatchObject({ code: "ELEVEN_KEY_INVALID" });
  expect(toEngineError("ELEVEN_OFFLINE").code).toBe("ELEVEN_OFFLINE");
  expect(toEngineError("ELEVEN_FAILED").code).toBe("ELEVEN_FAILED");
  expect(toEngineError("Không thấy file x")).toMatchObject({ code: "AGENT_FAILED", message: "Không thấy file x" });
});

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
