import { expect, test } from "vitest";
import { filterProjects, foldVi, NO_FILTER, recentProjects, RECENT_MAX } from "./library";
import type { ProjectSummary } from "./types";

const P = (dir: string, title: string, niche = "thoi-trang", status: ProjectSummary["status"] = "done"): ProjectSummary =>
  ({ dir, title, niche, created: "2026-11-20", status, runCount: 1 });

test("recentProjects puts building first and caps at RECENT_MAX", () => {
  const list = Array.from({ length: 9 }, (_, i) => P(`/${i}`, `V${i}`));
  const r = recentProjects(list, { "/7": {} });
  expect(RECENT_MAX).toBe(6);
  expect(r.map((p) => p.dir)).toEqual(["/7", "/0", "/1", "/2", "/3", "/4"]);
});

test("foldVi strips case and Vietnamese marks", () => {
  expect(foldVi("Váy Hoa ĐỎ")).toBe("vay hoa do");
});

const list = [P("/a", "Váy hoa"), P("/b", "Son đỏ", "my-pham", "needs_review"), P("/c", "Áo sơ mi", "thoi-trang", "new")];

test("search ignores diacritics", () => {
  expect(filterProjects(list, {}, { ...NO_FILTER, q: "vay" }).map((p) => p.dir)).toEqual(["/a"]);
  expect(filterProjects(list, {}, { ...NO_FILTER, q: "SON DO" }).map((p) => p.dir)).toEqual(["/b"]);
});

test("niche and status filters", () => {
  expect(filterProjects(list, {}, { ...NO_FILTER, niche: "my-pham" }).map((p) => p.dir)).toEqual(["/b"]);
  expect(filterProjects(list, {}, { ...NO_FILTER, status: "new" }).map((p) => p.dir)).toEqual(["/c"]);
  // a building project matches only "building" (and "all")
  expect(filterProjects(list, { "/a": {} }, { ...NO_FILTER, status: "done" }).map((p) => p.dir)).toEqual([]);
  expect(filterProjects(list, { "/a": {} }, { ...NO_FILTER, status: "building" }).map((p) => p.dir)).toEqual(["/a"]);
});

test("sort keys", () => {
  expect(filterProjects(list, {}, { ...NO_FILTER, sort: "old" }).map((p) => p.dir)).toEqual(["/c", "/b", "/a"]);
  expect(filterProjects(list, {}, { ...NO_FILTER, sort: "name" }).map((p) => p.title)).toEqual(["Áo sơ mi", "Son đỏ", "Váy hoa"]);
});
