import type { ProjectSummary } from "./types";

export const RECENT_MAX = 6;

export type StatusFilter = "all" | "done" | "needs_review" | "building" | "new";
export type SortKey = "new" | "old" | "name";
export type LibraryFilter = { q: string; niche: string; status: StatusFilter; sort: SortKey };
export const NO_FILTER: LibraryFilter = { q: "", niche: "", status: "all", sort: "new" };

/** Building projects first, then the rest in list order (newest first), at most RECENT_MAX. */
export function recentProjects(projects: ProjectSummary[], builds: Record<string, unknown>): ProjectSummary[] {
  const building = projects.filter((p) => builds[p.dir]);
  const rest = projects.filter((p) => !builds[p.dir]);
  return [...building, ...rest].slice(0, RECENT_MAX);
}

/** Lower-case, no Vietnamese tone/vowel marks: "Váy ĐỎ" → "vay do". */
export function foldVi(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[đĐ]/g, "d").toLowerCase();
}

export function filterProjects(projects: ProjectSummary[], builds: Record<string, unknown>, f: LibraryFilter): ProjectSummary[] {
  const q = foldVi(f.q.trim());
  const out = projects.filter((p) => {
    if (q && !foldVi(p.title).includes(q)) return false;
    if (f.niche && p.niche !== f.niche) return false;
    const building = !!builds[p.dir];
    if (f.status === "building") return building;
    if (f.status !== "all") return !building && p.status === f.status;
    return true;
  });
  if (f.sort === "old") out.reverse();
  if (f.sort === "name") out.sort((a, b) => a.title.localeCompare(b.title, "vi"));
  return out;
}
