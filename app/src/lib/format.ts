import { NICHES } from "./niches";

export function hhmm(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
export const nicheLabel = (id: string) => NICHES.find((n) => n.id === id)?.label ?? id;
