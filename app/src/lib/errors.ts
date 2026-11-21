import { hhmm } from "./format";

const KNOWN = new Set([
  "RATE_LIMIT", "NO_AUTH", "SETUP_REQUIRED", "BAD_INPUT", "SOCIAL_AUTH", "SOCIAL_LIMIT", "SOCIAL_FAILED",
  "ELEVEN_KEY_INVALID", "ELEVEN_OFFLINE",
  "VOICE_AUTH", "VOICE_QUOTA", "VOICE_MISSING", "VOICE_LIMIT", "VOICE_FAILED",
]);

export type ErrorAction = "retry" | "settings" | "setup" | "none";
export type ErrorInfo = { title: string; detail: string; action: ErrorAction };

/** Where the error came from: social commands and caption writing get their own wording. */
export type ErrorContext = "social" | "caption";

export function describeError(e: { code: string; message: string; retry_at: string | null }, context?: ErrorContext): ErrorInfo {
  if (context && (e.code === "BAD_INPUT" || !KNOWN.has(e.code))) {
    const title = context === "caption" ? "Chưa viết được caption" : "Chưa đăng được";
    return { title, detail: e.message, action: e.code === "BAD_INPUT" ? "none" : "retry" };
  }
  switch (e.code) {
    case "RATE_LIMIT": {
      const t = e.retry_at ? hhmm(e.retry_at) : "";
      return {
        title: "Đã hết lượt Claude",
        detail: t ? `Thử lại lúc ${t}` : "Thử lại sau ít phút",
        action: "retry",
      };
    }
    case "NO_AUTH":
      return { title: "Chưa đăng nhập Claude", detail: "Đăng nhập Claude trong Cài đặt rồi thử lại.", action: "settings" };
    case "SETUP_REQUIRED":
      return { title: "Cần tải lại Claude", detail: e.message || "Thiếu thành phần của Claude.", action: "setup" };
    case "BAD_INPUT":
      return { title: "File không dùng được", detail: e.message, action: "none" };
    case "SOCIAL_AUTH":
      return { title: "Key bundle.social không dùng được", detail: e.message || "Nhập lại key ở Cài đặt → Kết nối.", action: "settings" };
    case "SOCIAL_LIMIT":
      return { title: "Hết lượt đăng của gói bundle.social", detail: e.message || "Thử lại sau hoặc nâng gói.", action: "none" };
    case "SOCIAL_FAILED":
      return { title: "Đăng bài lỗi", detail: e.message, action: "retry" };
    case "ELEVEN_KEY_INVALID":
    case "VOICE_AUTH":
      return { title: "Key ElevenLabs không đúng", detail: "Nhập lại key ở Cài đặt → Kết nối & MCP.", action: "settings" };
    case "ELEVEN_OFFLINE":
      return { title: "Không kết nối được ElevenLabs", detail: "Kiểm tra mạng rồi thử lại.", action: "retry" };
    case "VOICE_QUOTA":
      return { title: "Tài khoản ElevenLabs hết ký tự", detail: e.message || "Nạp thêm ký tự hoặc tắt lồng tiếng.", action: "none" };
    case "VOICE_MISSING":
      return { title: "Giọng đọc không còn trong tài khoản ElevenLabs, chọn giọng khác trong Cài đặt", detail: "", action: "settings" };
    case "VOICE_LIMIT":
      return { title: "ElevenLabs đang bận, thử lại sau", detail: "", action: "retry" };
    case "VOICE_FAILED":
      return { title: "Lồng tiếng bị lỗi", detail: e.message, action: "retry" };
    default:
      return { title: "Dựng video bị lỗi", detail: e.message, action: "retry" };
  }
}

export type AnyEngineError = { code: string; message: string; retry_at: string | null };

/** Normalise whatever a rejected promise carried into the engine error shape. */
export function toEngineError(e: unknown): AnyEngineError {
  if (e && typeof e === "object" && "code" in e && typeof (e as { code: unknown }).code === "string") {
    const x = e as Partial<AnyEngineError>;
    return { code: x.code as string, message: x.message ?? "", retry_at: x.retry_at ?? null };
  }
  // App commands reject with a bare code string (for example "ELEVEN_OFFLINE").
  if (typeof e === "string" && KNOWN.has(e)) return { code: e, message: "", retry_at: null };
  const message = e instanceof Error ? e.message : typeof e === "string" ? e : "Có lỗi xảy ra";
  return { code: "AGENT_FAILED", message, retry_at: null };
}
