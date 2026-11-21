const MESSAGES: Record<string, string> = {
  LICENSE_INVALID: "Key không đúng",
  LICENSE_USED: "Key đã được kích hoạt trên máy khác. Liên hệ người bán để được hỗ trợ.",
  LICENSE_REVOKED: "Key đã bị thu hồi",
  LICENSE_OFFLINE: "Không kết nối được máy chủ kích hoạt, kiểm tra mạng rồi thử lại",
};
export const licenseMessage = (code: unknown) => MESSAGES[String(code)] ?? MESSAGES.LICENSE_OFFLINE;
