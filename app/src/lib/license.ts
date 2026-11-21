const MESSAGES: Record<string, string> = {
  LICENSE_INVALID: "Key không đúng",
  LICENSE_USED: "Key đã được kích hoạt trên máy khác. Liên hệ người bán để được hỗ trợ.",
  LICENSE_REVOKED: "Key đã bị thu hồi",
  LICENSE_OFFLINE: "Không kết nối được máy chủ kích hoạt, kiểm tra mạng rồi thử lại",
  LICENSE_REQUIRED: "Cần kích hoạt AutoEdit trước",
  LICENSE_MACHINE: "Không đọc được thông tin máy này. Liên hệ người bán để được hỗ trợ.",
  LICENSE_STORE: "Không lưu được key vào Keychain. Cho phép AutoEdit truy cập Keychain rồi thử lại.",
  LICENSE_CONFIG: "Bản cài đặt bị lỗi cấu hình kích hoạt. Liên hệ người bán.",
};
export const licenseMessage = (code: unknown) => MESSAGES[String(code)] ?? MESSAGES.LICENSE_OFFLINE;

const KEY_BODY = /^[0-9A-HJKMNP-TV-Z]{16}$/;

/** Same rules as the Worker's normKey and the CLI's norm (shared vectors: license-server/test/key-vectors.json). */
export function normalizeKey(raw: string): string {
  const s = raw.normalize("NFKC").replace(/[\s​-‍﻿]/g, "")
    .replace(/[‐-―−]/g, "-").toUpperCase();
  if (!s.startsWith("AE")) return s;
  const body = s.slice(2).replace(/^-/, "").replace(/O/g, "0").replace(/[IL]/g, "1");
  const flat = body.replace(/-/g, "");
  if (KEY_BODY.test(flat)) return `AE-${flat.slice(0, 4)}-${flat.slice(4, 8)}-${flat.slice(8, 12)}-${flat.slice(12)}`;
  return `AE-${body}`;
}
