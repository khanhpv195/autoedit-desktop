import { hhmm } from "./format";

export type ErrorAction = "retry" | "settings" | "setup" | "none";
export type ErrorInfo = { title: string; detail: string; action: ErrorAction };

export function describeError(e: { code: string; message: string; retry_at: string | null }): ErrorInfo {
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
  const message = e instanceof Error ? e.message : typeof e === "string" ? e : "Có lỗi xảy ra";
  return { code: "AGENT_FAILED", message, retry_at: null };
}
