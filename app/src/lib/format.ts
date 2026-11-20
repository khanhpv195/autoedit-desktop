import { NICHES } from "./niches";

export function hhmm(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
export const nicheLabel = (id: string) => NICHES.find((n) => n.id === id)?.label ?? id;

const p2 = (n: number) => String(n).padStart(2, "0");
/** ISO 8601 with the local UTC offset, for the engine and bundle.social. */
export function localIso(d: Date): string {
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const a = Math.abs(off);
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}T${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}${sign}${p2(Math.floor(a / 60))}:${p2(a % 60)}`;
}
/** Value for an `<input type="datetime-local">` in local time. */
export const toInputValue = (d: Date) => `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}T${p2(d.getHours())}:${p2(d.getMinutes())}`;
/** "19:30 20/11" in local time. */
export function postTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : `${hhmm(iso)} ${p2(d.getDate())}/${p2(d.getMonth() + 1)}`;
}
export const CHANNELS: Record<string, string> = { TIKTOK: "TikTok", INSTAGRAM: "Instagram", YOUTUBE: "YouTube Shorts", FACEBOOK: "Facebook Reels" };
export const V2_CHANNELS = Object.keys(CHANNELS);
export const channelLabel = (t: string) => CHANNELS[t] ?? t;

/** Monday 00:00 (local) of the week `offset` weeks from `now`, and the next Monday 00:00. */
export function weekRange(now: Date, offset = 0): { from: Date; to: Date } {
  const from = new Date(now.getFullYear(), now.getMonth(), now.getDate() - ((now.getDay() + 6) % 7) + offset * 7);
  const to = new Date(from.getFullYear(), from.getMonth(), from.getDate() + 7);
  return { from, to };
}

export const STATUS_VI: Record<string, string> = { SCHEDULED: "Đã lên lịch", POSTED: "Đã đăng", ERROR: "Lỗi", PROCESSING: "Đang xử lý" };
