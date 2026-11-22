# Video library + sidebar restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sidebar shows nav + max 6 recent videos; a new "Thư viện" page shows every video as a thumbnail grid with search/filter/sort; the engine produces `thumb.jpg` per run and backfills old runs.

**Architecture:** Engine (Python) writes `runs/N/thumb.jpg` after each render and gains an `autoedit thumbs --root R` backfill command. Rust `ProjectSummary` exposes the last run's thumb path. Frontend: pure list helpers in `lib/library.ts`, shared project actions (rename/delete) extracted from `Sidebar.tsx`, new `screens/Library.tsx`; backfill runs through the existing generic `engine_run` command (`runEngine`).

**Tech Stack:** Python 3 + ffmpeg (engine, pytest via `uv`), Rust/Tauri 2 (cargo test), React 18 + TypeScript + Vite (vitest + testing-library).

**Spec:** `docs/superpowers/specs/2026-11-22-video-library-design.md`

## Global Constraints

- UI copy is Vietnamese, exactly as written in this plan.
- `RECENT_MAX = 6` recent projects in the sidebar; building projects first, then list order (newest first).
- Thumbnail: ffmpeg frame at t=1.0 s, falling back to t=0 when that yields no image; `scale=360:-2`; `-q:v 4`; written atomically; file name `runs/<n>/thumb.jpg`.
- A thumbnail failure never fails or aborts an edit run and never raises out of `make_thumb`.
- `ProjectSummary.thumb` = absolute path of the **last** run's `thumb.jpg`, only when that file exists; otherwise null.
- Search is case- and diacritic-insensitive (NFD + strip U+0300–U+036F, `đ/Đ → d`).
- No new npm, cargo or Python dependencies.
- Commands: engine `cd engine && uv run pytest -q -W error`; Rust `cd app/src-tauri && cargo test && cargo clippy --all-targets -- -D warnings`; frontend `cd app && npx vitest run` and `npm run build`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

**Spec amendment (ruling):** the spec mentions a Rust command `backfill_thumbs`; the existing generic `engine_run(args)` already spawns any engine subcommand with events, so the frontend calls `runEngine(["thumbs","--root",root])` instead. No new Rust command.

---

### Task 1: Engine thumbnails (`make_thumb`, edit hook, `thumbs` command)

**Files:**
- Create: `engine/autoedit/render/thumb.py`
- Modify: `engine/autoedit/cli.py` (`_edit` after `_render_with_retry`; new `_thumbs`; `main` parser + handler map)
- Test: `engine/tests/test_thumb.py`

**Interfaces:**
- Produces: `make_thumb(video: Path, out: Path) -> bool`; `backfill(root: Path, on_made: Callable[[Path], None]) -> int`; CLI `autoedit thumbs --root <dir>` emitting `{"type":"thumb","dir":"<project dir>"}` per thumb made and finally `{"type":"thumbs_done","made":<int>}`.

- [ ] **Step 1: Write failing tests** — `engine/tests/test_thumb.py`:

```python
import json
from pathlib import Path

from autoedit import cli
from autoedit.render import thumb as thumb_mod
from autoedit.render.thumb import backfill, make_thumb
from tests.conftest import _make


def test_make_thumb_writes_jpeg(clip, tmp_path):
    out = tmp_path / "thumb.jpg"
    assert make_thumb(clip, out) is True
    assert out.read_bytes()[:2] == b"\xff\xd8"
    assert not list(tmp_path.glob("*.part*"))


def test_make_thumb_short_clip(tmp_path):
    short = _make(tmp_path / "short.mp4", 360, 640, 0.5)
    out = tmp_path / "thumb.jpg"
    assert make_thumb(short, out) is True and out.stat().st_size > 0


def test_make_thumb_bad_input_returns_false(tmp_path):
    bad = tmp_path / "bad.mp4"; bad.write_bytes(b"not a video")
    out = tmp_path / "thumb.jpg"
    assert make_thumb(bad, out) is False
    assert not out.exists()
    assert make_thumb(tmp_path / "missing.mp4", out) is False


def _project(root: Path, name: str, runs: list[int], clip: Path | None) -> Path:
    d = root / name; d.mkdir(parents=True)
    (d / "project.json").write_text(json.dumps({"niche": "chung", "runs": [{"n": n} for n in runs]}))
    for n in runs:
        (d / "runs" / str(n)).mkdir(parents=True)
        if clip is not None:
            (d / "runs" / str(n) / "final.mp4").write_bytes(clip.read_bytes())
    return d


def test_backfill_makes_only_missing_last_run_thumbs(clip, tmp_path):
    root = tmp_path / "projects"
    a = _project(root, "a", [1, 2], clip)
    b = _project(root, "b", [1], clip); (b / "runs" / "1" / "thumb.jpg").write_bytes(b"x")
    _project(root, "c", [], None)
    _project(root, "d", [1], None)                       # run without final.mp4
    (root / "e").mkdir(); (root / "e" / "project.json").write_text("{broken")
    made: list[Path] = []
    assert backfill(root, made.append) == 1
    assert made == [a]
    assert (a / "runs" / "2" / "thumb.jpg").exists() and not (a / "runs" / "1" / "thumb.jpg").exists()
    assert (b / "runs" / "1" / "thumb.jpg").read_bytes() == b"x"


def test_backfill_missing_root(tmp_path):
    assert backfill(tmp_path / "nope", lambda d: None) == 0


def test_thumbs_command_events(clip, tmp_path, capsys):
    root = tmp_path / "projects"
    a = _project(root, "a", [1], clip)
    assert cli.main(["thumbs", "--root", str(root)]) == 0
    ev = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    assert ev == [{"type": "thumb", "dir": str(a)}, {"type": "thumbs_done", "made": 1}]
```

Append to `engine/tests/test_cli.py` (after `test_edit_happy_path`, reusing its fixtures and fake agent shape):

```python
def _fake_agent_ok(session, prompt, options, **kw):
    async def run():
        session.edl, _ = validate_edl({"keep": [{"start": 0.6, "end": 1.8}, {"start": 3.2, "end": 4.4}]},
                                      WORDS, session.prepared.info.duration)
        session.summary, session.finished = ["ok"], True
        return AgentOutcome(True, 1, None)
    return run()


def test_edit_writes_thumb(project, monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_agent", _fake_agent_ok)
    assert cli.main(["edit", "--project", str(project), "--prompt", "x"]) == 0
    assert (project / "runs" / "1" / "thumb.jpg").exists()


def test_edit_survives_thumb_failure(project, monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_agent", _fake_agent_ok)
    monkeypatch.setattr(cli, "make_thumb", lambda v, o: False)
    assert cli.main(["edit", "--project", str(project), "--prompt", "x"]) == 0
    pj = json.loads((project / "project.json").read_text())
    assert pj["runs"][0]["n"] == 1 and not (project / "runs" / "1" / "thumb.jpg").exists()
```

(If `from tests.conftest import _make` does not resolve in this repo's pytest layout, copy `_make` into the test file instead; keep the test bodies.)

- [ ] **Step 2: Run and see them fail** — `cd engine && uv run pytest tests/test_thumb.py tests/test_cli.py -q -W error` → ImportError / no `thumbs` command.

- [ ] **Step 3: Implement** — `engine/autoedit/render/thumb.py`:

```python
"""Poster frame of a rendered video, for the app's library grid."""
import json
import sys
from pathlib import Path
from typing import Callable

from autoedit import bins

THUMB_WIDTH = 360
THUMB_NAME = "thumb.jpg"


def make_thumb(video: Path, out: Path) -> bool:
    """Write a JPEG frame of `video` to `out` (t=1 s, or the first frame for very short videos).
    Returns False on any failure; never raises: a missing thumbnail must not fail an edit."""
    tmp = out.with_name(out.stem + ".part.jpg")
    try:
        if not video.is_file():
            return False
        for t in (1.0, 0.0):
            tmp.unlink(missing_ok=True)
            try:
                bins.run([bins.tool_path("ffmpeg"), "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
                          "-frames:v", "1", "-vf", f"scale={THUMB_WIDTH}:-2", "-q:v", "4", str(tmp)])
            except Exception as err:   # noqa: BLE001 — ffmpeg failure at this seek point; try the next one
                print(f"thumb: {err}", file=sys.stderr)
                continue
            if tmp.is_file() and tmp.stat().st_size > 0:
                tmp.replace(out)
                return True
        return False
    except Exception as err:   # noqa: BLE001
        print(f"thumb: {err}", file=sys.stderr)
        return False
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def backfill(root: Path, on_made: Callable[[Path], None]) -> int:
    """Make the missing thumbnail of each project's last run under `root`. Returns how many were made."""
    if not root.is_dir():
        return 0
    made = 0
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            data = json.loads((d / "project.json").read_text(encoding="utf-8"))
            runs = data.get("runs") or []
            n = runs[-1].get("n") if runs else None
        except (OSError, ValueError, AttributeError):
            continue
        if n is None:
            continue
        run_dir = d / "runs" / str(n)
        final, thumb = run_dir / "final.mp4", run_dir / THUMB_NAME
        if not final.is_file() or thumb.exists():
            continue
        if make_thumb(final, thumb):
            made += 1
            on_made(d)
    return made
```

In `engine/autoedit/cli.py`:
- import: `from autoedit.render.thumb import THUMB_NAME, backfill, make_thumb`
- in `_edit`, directly after `res, edl, summary = _render_with_retry(...)` (same indentation):
  ```python
                make_thumb(res.path, run_dir / THUMB_NAME)     # best effort: never fails the run
  ```
- new handler next to the others:
  ```python
  async def _thumbs(args, events: Emitter) -> int:
      made = backfill(Path(args.root), lambda d: events.emit_raw({"type": "thumb", "dir": str(d)}))
      events.emit_raw({"type": "thumbs_done", "made": made})
      return 0
  ```
- parser: `t = sub.add_parser("thumbs"); t.add_argument("--root", required=True)`; handler map: `"thumbs": _thumbs`.

- [ ] **Step 4: Run** `cd engine && uv run pytest tests/test_thumb.py tests/test_cli.py -q -W error` → PASS; then full `uv run pytest -q -W error` → no new failures.

- [ ] **Step 5: Commit** `feat(engine): thumb.jpg per run + 'autoedit thumbs' backfill`.

---

### Task 2: Rust `ProjectSummary.thumb`

**Files:**
- Modify: `app/src-tauri/src/projects.rs` (struct `ProjectSummary` ~line 24, `summary()` ~line 259–297, tests module)

**Interfaces:**
- Produces: JSON field `thumb: string | null` on every `ProjectSummary` (serde camelCase → `thumb`).

- [ ] **Step 1: Failing test** — in the `#[cfg(test)]` module, using the existing `new_project`, `read_json`, `write_json` helpers:

```rust
    #[test]
    fn summary_thumb_is_last_runs_existing_thumb() {
        let root = tempfile::tempdir().unwrap();
        let dir = new_project(root.path(), "", "");
        assert_eq!(detail(&dir).unwrap().summary.thumb, None);
        let mut m = read_json(&dir).unwrap();
        m.insert("runs".into(), json!([{"n": 1}, {"n": 2}]));
        write_json(&dir, &m).unwrap();
        for n in ["1", "2"] { std::fs::create_dir_all(dir.join("runs").join(n)).unwrap(); }
        std::fs::write(dir.join("runs/1/thumb.jpg"), b"x").unwrap();
        // only run 1 has a thumb, but run 2 is the last one
        assert_eq!(detail(&dir).unwrap().summary.thumb, None);
        std::fs::write(dir.join("runs/2/thumb.jpg"), b"x").unwrap();
        let want = dir.join("runs").join("2").join("thumb.jpg").to_string_lossy().into_owned();
        assert_eq!(detail(&dir).unwrap().summary.thumb, Some(want));
    }
```

(Adjust only the helper/field access if `detail(..).summary` is spelled differently; the existing test `summary_counts_future_scheduled_posts` shows the access path.)

- [ ] **Step 2:** `cd app/src-tauri && cargo test summary_thumb` → compile error (no field).

- [ ] **Step 3: Implement** — add to the struct after `scheduled_posts`:

```rust
    /// Poster frame of the last run (`runs/<n>/thumb.jpg`), when it exists.
    pub thumb: Option<String>,
```

In `summary()`, after `let runs = ...`:

```rust
    let thumb = runs
        .last()
        .and_then(|r| r.get("n"))
        .and_then(Value::as_u64)
        .map(|n| dir.join("runs").join(n.to_string()).join("thumb.jpg"))
        .filter(|p| p.is_file())
        .map(|p| p.to_string_lossy().into_owned());
```

and `thumb,` in the `ProjectSummary { .. }` literal. Fix any other construction sites the compiler reports.

- [ ] **Step 4:** `cd app/src-tauri && cargo test && cargo clippy --all-targets -- -D warnings` → PASS, no warnings.

- [ ] **Step 5: Commit** `feat(app): ProjectSummary.thumb — last run's poster frame`.

---

### Task 3: Frontend types + pure list helpers

**Files:**
- Create: `app/src/lib/library.ts`, `app/src/lib/library.test.ts`
- Modify: `app/src/lib/types.ts` (`ProjectSummary`, `EngineEvent`), `app/src/state/store.tsx` (`Route`), `app/src/App.tsx` (temporary `library` case), `app/src/lib/engine.ts` (`backfillThumbs`)

**Interfaces:**
- Produces:
  - `ProjectSummary.thumb?: string | null`
  - `EngineEvent` adds `| { type: "thumb"; dir: string } | { type: "thumbs_done"; made: number }`
  - `Route` adds `| { name: "library" }`
  - `export const RECENT_MAX = 6;`
  - `export function recentProjects(projects: ProjectSummary[], builds: Record<string, unknown>): ProjectSummary[]`
  - `export function foldVi(s: string): string`
  - `export type StatusFilter = "all" | "done" | "needs_review" | "building" | "new";`
  - `export type SortKey = "new" | "old" | "name";`
  - `export type LibraryFilter = { q: string; niche: string /* "" = all */; status: StatusFilter; sort: SortKey };`
  - `export const NO_FILTER: LibraryFilter = { q: "", niche: "", status: "all", sort: "new" };`
  - `export function filterProjects(projects: ProjectSummary[], builds: Record<string, unknown>, f: LibraryFilter): ProjectSummary[]`
  - `export async function backfillThumbs(root: string, onThumb: () => void): Promise<void>` in `lib/engine.ts`

- [ ] **Step 1: Failing tests** — `app/src/lib/library.test.ts`:

```ts
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
```

- [ ] **Step 2:** `cd app && npx vitest run src/lib/library.test.ts` → FAIL (module missing).

- [ ] **Step 3: Implement** — `app/src/lib/library.ts`:

```ts
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
```

`types.ts`: add `thumb?: string | null;` to `ProjectSummary` (doc comment: poster frame of the last run) and the two `EngineEvent` members. `store.tsx`: add `| { name: "library" }` to `Route`. `App.tsx` `Screen()`: add `case "library": return null;` (Task 5 replaces it). `engine.ts`:

```ts
/** Make the missing poster frames of older runs; `onThumb` fires after each one. */
export async function backfillThumbs(root: string, onThumb: () => void): Promise<void> {
  await runEngine(["thumbs", "--root", root], (e) => { if (e.type === "thumb") onThumb(); }).result;
}
```

- [ ] **Step 4:** `cd app && npx vitest run && npm run build` → PASS.

- [ ] **Step 5: Commit** `feat(app): library list helpers, thumb/route/event types`.

---

### Task 4: Shared project actions + new sidebar

**Files:**
- Create: `app/src/components/ProjectActions.tsx`
- Modify: `app/src/components/Sidebar.tsx`, `app/src/styles.css` (sidebar section ~lines 36–75), `app/src/components/Sidebar.test.tsx`

**Interfaces:**
- Consumes: `recentProjects`, `RECENT_MAX` from `lib/library.ts`; `Route` `{ name: "library" }`.
- Produces (from `ProjectActions.tsx`, used by Task 5):
  - `export function useProjectActions(): { menu: string | null; setMenu(d: string | null): void; renaming: string | null; setRenaming(d: string | null): void; deleting: ProjectSummary | null; setDeleting(p: ProjectSummary | null): void; busy: boolean; rename(p: ProjectSummary, name: string): Promise<void>; remove(p: ProjectSummary): Promise<void> }` — the state, click-outside effect for the ⋯ menu, and the `rename`/`remove` functions moved **unchanged** from `Sidebar.tsx`.
  - `export function NameInput(...)` and `export function ConfirmDelete(...)` — moved verbatim from `Sidebar.tsx`.
  - `export function ProjectMenu({ p, actions }: { p: ProjectSummary; actions: ReturnType<typeof useProjectActions> })` — renders the ⋯ button (`className="more"`, same aria-label/aria-expanded) plus, when open, the `.pmenu` with "Đổi tên" / "Xoá…", exactly as the current sidebar markup.
  - `export function DeleteDialog({ actions }: { actions: ReturnType<typeof useProjectActions> })` — renders `ConfirmDelete` for `actions.deleting` (with `building` from store), or nothing.

- [ ] **Step 1: Failing tests** — update `Sidebar.test.tsx`:
  - Keep every existing test (they must still pass unchanged except where noted below).
  - Add:

```tsx
const many = Array.from({ length: 8 }, (_, i) => ({
  dir: `/p${i}`, title: `Video ${i}`, niche: "thoi-trang", created: "2026-11-20", status: "done" as const, runCount: 1,
}));

test("shows at most 6 recent projects and a 'Xem tất cả' link to the library", async () => {
  m.licenseStatus.mockResolvedValue({ licensed: true, name: "Test" });
  m.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true });
  m.listProjects.mockResolvedValue(many);
  render(<StoreProvider><Sidebar /><Probe /></StoreProvider>);
  expect(await screen.findByText("Video 0")).toBeInTheDocument();
  expect(screen.getByText("Video 5")).toBeInTheDocument();
  expect(screen.queryByText("Video 6")).toBeNull();
  expect(screen.getByText("Gần đây")).toBeInTheDocument();
  await userEvent.click(screen.getByText(/Xem tất cả/));
  expect(screen.getByTestId("route").textContent).toContain('"library"');
});

test("'Thư viện' nav shows the total and opens the library; no 'Xem tất cả' when all fit", async () => {
  m.licenseStatus.mockResolvedValue({ licensed: true, name: "Test" });
  m.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/p", lastNiche: null, onboarded: true });
  m.listProjects.mockResolvedValue(many.slice(0, 3));
  render(<StoreProvider><Sidebar /><Probe /></StoreProvider>);
  await screen.findByText("Video 0");
  expect(screen.queryByText(/Xem tất cả/)).toBeNull();
  const nav = screen.getByText("Thư viện").closest(".sn")!;
  expect(nav).toHaveTextContent("3");
  await userEvent.click(nav);
  expect(screen.getByTestId("route").textContent).toContain('"library"');
});
```

- [ ] **Step 2:** `cd app && npx vitest run src/components/Sidebar.test.tsx` → new tests FAIL.

- [ ] **Step 3: Implement**
  - Create `ProjectActions.tsx` by moving `NameInput`, `ConfirmDelete`, the `menu/renaming/deleting/busy` state, the click-outside `useEffect`, `rename()` and `remove()` out of `Sidebar.tsx` into `useProjectActions()` (it calls `useStore()` itself for `state, go, notify, refreshProjects`; `remove` still navigates to `{ name: "niche" }` when the deleted project is the one open). Add `ProjectMenu` and `DeleteDialog` as described in Interfaces, reproducing the current markup and classes.
  - `Sidebar.tsx` new structure (keep `aside.side#side`, brand, `.newbtn`, `.sidefoot` contents and copyright unchanged):

```tsx
  const recent = recentProjects(state.projects, state.builds);
  const lib = state.route.name === "library";
  const sched = state.route.name === "schedule";
  ...
      <button className="newbtn" ...>…Video mới</button>
      <div className="snav">
        <div className={"sn" + (lib ? " on" : "")} role="button" tabIndex={0}
          onClick={() => go({ name: "library" })} onKeyDown={(e) => { if (e.key === "Enter") go({ name: "library" }); }}>
          <LayoutGrid className="i" aria-hidden />Thư viện<span className="cnt">{n}</span></div>
        {/* Lịch đăng: same two branches as today, with " on" when sched */}
      </div>
      {recent.length > 0 && <div className="slabel">Gần đây</div>}
      <div className="plist">
        {recent.map((p) => /* the existing .pi row, with <ProjectMenu p={p} actions={actions} /> in place of the inline button+menu */)}
        {n > recent.length && (
          <div className="seeall" role="button" tabIndex={0} onClick={() => go({ name: "library" })}
            onKeyDown={(e) => { if (e.key === "Enter") go({ name: "library" }); }}>Xem tất cả →</div>
        )}
      </div>
      ...
      <DeleteDialog actions={actions} />
```

  `LayoutGrid` comes from `lucide-react` (already a dependency). The `Clapperboard` "Video" toggle item is removed (the "Video mới" button and the recent list replace it). Remove now-unused imports.
  - CSS (`styles.css`): make `.snav` a vertical list: `.snav{display:flex;flex-direction:column;gap:2px;margin:0 8px 10px}`; `.sn{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:var(--r);font-size:13px;font-weight:600;color:var(--ink2);cursor:pointer}`; `.sn:hover{background:#efeff2}`; `.sn.on{background:#fff;color:var(--ink);box-shadow:var(--sh-sm),0 0 0 1px var(--line)}`; keep `.sn.off`; `.sn .i{width:16px;height:16px}`; `.sn .cnt{margin-left:auto;font-size:11px;font-weight:600;color:var(--faint)}`; `.slabel{margin:4px 18px 4px;font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--faint)}`; `.seeall{margin:4px 10px;padding:6px 0;font-size:12px;font-weight:600;color:var(--accent);cursor:pointer}`. Replace the old `.snav`/`.sn` rules rather than adding duplicates; check that the `newbtn` placement still looks right (button above nav).
  - Note: the label "Gần đây" is rendered as text "Gần đây" and upper-cased by CSS — the test looks for "Gần đây".

- [ ] **Step 4:** `cd app && npx vitest run && npm run build` → PASS (all pre-existing Sidebar tests included).

- [ ] **Step 5: Commit** `feat(app): sidebar nav + 'Gần đây' (max 6), shared project actions`.

---

### Task 5: Library screen + thumbnail backfill

**Files:**
- Create: `app/src/screens/Library.tsx`, `app/src/screens/Library.test.tsx`
- Modify: `app/src/App.tsx` (`case "library": return <Library />;`), `app/src/styles.css` (append a `/* ---------- library ---------- */` section)

**Interfaces:**
- Consumes: `filterProjects`, `NO_FILTER`, `LibraryFilter`, `StatusFilter`, `SortKey` (`lib/library.ts`); `useProjectActions`, `ProjectMenu`, `NameInput`, `DeleteDialog` (`components/ProjectActions.tsx`); `backfillThumbs` (`lib/engine.ts`); `api.fileSrc`; `nicheLabel` (`lib/format.ts`).
- Produces: `export default function Library()`; `export function resetBackfillForTests(): void`.

- [ ] **Step 1: Failing tests** — `app/src/screens/Library.test.tsx`:

```tsx
import { vi, test, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import * as engine from "../lib/engine";
import { StoreProvider, useStore } from "../state/store";
import Library, { resetBackfillForTests } from "./Library";

vi.mock("../lib/api");
vi.mock("../lib/engine");
const m = vi.mocked(api);
const e = vi.mocked(engine);

function Probe() {
  const { state } = useStore();
  return <div data-testid="route">{JSON.stringify(state.route)}</div>;
}

const P = (dir: string, title: string, extra: Partial<api.ProjectSummaryLike> = {}) =>
  ({ dir, title, niche: "thoi-trang", created: "2026-11-20", status: "done", runCount: 1, thumb: `${dir}/runs/1/thumb.jpg`, ...extra });

function boot(projects: unknown[]) {
  m.licenseStatus.mockResolvedValue({ licensed: true, name: "Test" });
  m.getSettings.mockResolvedValue({ model: "m", projectsRoot: "/root", lastNiche: null, onboarded: true });
  m.listProjects.mockResolvedValue(projects as never);
  m.fileSrc.mockImplementation((p: string) => "asset://" + p);
  e.backfillThumbs.mockResolvedValue();
}

beforeEach(() => { vi.clearAllMocks(); resetBackfillForTests(); });

test("grid shows every project with its thumbnail and opens one on click", async () => {
  boot([P("/a", "Váy hoa"), P("/b", "Son đỏ", { niche: "my-pham", thumb: null, runCount: 0, status: "new" })]);
  render(<StoreProvider><Library /><Probe /></StoreProvider>);
  expect(await screen.findByText("Váy hoa")).toBeInTheDocument();
  expect(screen.getByText(/2 video/)).toBeInTheDocument();
  expect(screen.getByAltText("Váy hoa")).toHaveAttribute("src", "asset:///a/runs/1/thumb.jpg");
  expect(screen.queryByAltText("Son đỏ")).toBeNull();
  await userEvent.click(screen.getByText("Son đỏ"));
  expect(screen.getByTestId("route").textContent).toContain('"/b"');
});

test("search without diacritics, then clear filters from the empty state", async () => {
  boot([P("/a", "Váy hoa"), P("/b", "Son đỏ")]);
  render(<StoreProvider><Library /></StoreProvider>);
  await screen.findByText("Váy hoa");
  await userEvent.type(screen.getByPlaceholderText("Tìm theo tên…"), "son do");
  expect(screen.queryByText("Váy hoa")).toBeNull();
  expect(screen.getByText("Son đỏ")).toBeInTheDocument();
  await userEvent.type(screen.getByPlaceholderText("Tìm theo tên…"), "xyz");
  expect(screen.getByText("Không có video khớp bộ lọc")).toBeInTheDocument();
  await userEvent.click(screen.getByText("Xoá bộ lọc"));
  expect(screen.getByText("Váy hoa")).toBeInTheDocument();
});

test("status filter", async () => {
  boot([P("/a", "Váy hoa"), P("/b", "Son đỏ", { status: "needs_review" })]);
  render(<StoreProvider><Library /></StoreProvider>);
  await screen.findByText("Váy hoa");
  await userEvent.selectOptions(screen.getByLabelText("Trạng thái"), "needs_review");
  expect(screen.queryByText("Váy hoa")).toBeNull();
  expect(screen.getByText("Son đỏ")).toBeInTheDocument();
});

test("empty library offers 'Video mới'", async () => {
  boot([]);
  render(<StoreProvider><Library /><Probe /></StoreProvider>);
  expect(await screen.findByText("Chưa có video nào")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Video mới/ }));
  expect(screen.getByTestId("route").textContent).toContain('"niche"');
});

test("backfills missing thumbnails once per session", async () => {
  boot([P("/a", "Váy hoa", { thumb: null })]);
  const { unmount } = render(<StoreProvider><Library /></StoreProvider>);
  await waitFor(() => expect(e.backfillThumbs).toHaveBeenCalledTimes(1));
  expect(e.backfillThumbs.mock.calls[0][0]).toBe("/root");
  unmount();
  render(<StoreProvider><Library /></StoreProvider>);
  await screen.findByText("Váy hoa");
  expect(e.backfillThumbs).toHaveBeenCalledTimes(1);
});

test("no backfill when every built project has a thumbnail", async () => {
  boot([P("/a", "Váy hoa"), P("/b", "Mới", { thumb: null, runCount: 0, status: "new" })]);
  render(<StoreProvider><Library /></StoreProvider>);
  await screen.findByText("Váy hoa");
  expect(e.backfillThumbs).not.toHaveBeenCalled();
});
```

(Replace `api.ProjectSummaryLike` with `ProjectSummary` imported from `../lib/types`. If the store's boot path needs other `api`/`engine` mocks resolved — compare with `Sidebar.test.tsx` and `Settings.test.tsx` — add them the same way; do not weaken assertions.)

- [ ] **Step 2:** `cd app && npx vitest run src/screens/Library.test.tsx` → FAIL.

- [ ] **Step 3: Implement** — `app/src/screens/Library.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import { Film, Plus } from "lucide-react";
import { useStore } from "../state/store";
import * as api from "../lib/api";
import { backfillThumbs } from "../lib/engine";
import { nicheLabel } from "../lib/format";
import { filterProjects, NO_FILTER, type LibraryFilter, type SortKey, type StatusFilter } from "../lib/library";
import { DeleteDialog, NameInput, ProjectMenu, useProjectActions } from "../components/ProjectActions";

const DOT = { new: "new", done: "done", needs_review: "review" } as const;

let backfillStarted = false;
export function resetBackfillForTests() { backfillStarted = false; }

export default function Library() {
  const { state, go, refreshProjects } = useStore();
  const actions = useProjectActions();
  const [f, setF] = useState<LibraryFilter>(NO_FILTER);
  const all = state.projects;
  const shown = useMemo(() => filterProjects(all, state.builds, f), [all, state.builds, f]);
  const niches = useMemo(() => [...new Set(all.map((p) => p.niche))], [all]);

  useEffect(() => {
    const root = state.settings?.projectsRoot;
    if (backfillStarted || !root || !all.some((p) => p.runCount > 0 && !p.thumb)) return;
    backfillStarted = true;
    backfillThumbs(root, () => void refreshProjects()).then(() => refreshProjects()).catch(() => {});
  }, [all, state.settings, refreshProjects]);

  if (all.length === 0) {
    return (
      <div className="lib">
        <h2>Thư viện video</h2>
        <div className="lib-empty">
          <b>Chưa có video nào</b>
          <button className="btn primary" onClick={() => go({ name: "niche" })}><Plus size={16} aria-hidden />Video mới</button>
        </div>
      </div>
    );
  }

  return (
    <div className="lib">
      <h2>Thư viện video <span className="muted">· {all.length} video</span></h2>
      <div className="lib-bar">
        <input type="search" placeholder="Tìm theo tên…" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} />
        <select aria-label="Ngách" value={f.niche} onChange={(e) => setF({ ...f, niche: e.target.value })}>
          <option value="">Tất cả ngách</option>
          {niches.map((n) => <option key={n} value={n}>{nicheLabel(n)}</option>)}
        </select>
        <select aria-label="Trạng thái" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as StatusFilter })}>
          <option value="all">Tất cả trạng thái</option>
          <option value="done">Xong</option>
          <option value="needs_review">Cần xem lại</option>
          <option value="building">Đang dựng</option>
          <option value="new">Mới</option>
        </select>
        <select aria-label="Sắp xếp" value={f.sort} onChange={(e) => setF({ ...f, sort: e.target.value as SortKey })}>
          <option value="new">Mới nhất</option>
          <option value="old">Cũ nhất</option>
          <option value="name">Tên A–Z</option>
        </select>
      </div>
      {shown.length === 0 ? (
        <div className="lib-empty">
          <b>Không có video khớp bộ lọc</b>
          <button className="btn ghost" onClick={() => setF(NO_FILTER)}>Xoá bộ lọc</button>
        </div>
      ) : (
        <div className="lib-grid">
          {shown.map((p) => {
            const building = !!state.builds[p.dir];
            return (
              <div key={p.dir} className="lib-card" role="button" tabIndex={0}
                onClick={() => { if (actions.renaming !== p.dir) go({ name: "project", dir: p.dir }); }}
                onKeyDown={(e) => { if (e.key === "Enter" && actions.renaming !== p.dir) go({ name: "project", dir: p.dir }); }}>
                <div className="lib-thumb">
                  {building ? <span className="lib-ph">đang dựng…</span>
                    : p.thumb ? <img src={api.fileSrc(p.thumb)} alt={p.title} loading="lazy" />
                    : <Film className="lib-ph" aria-hidden />}
                  <i className={"st " + (building ? "run" : DOT[p.status])} />
                </div>
                <div className="lib-meta">
                  {actions.renaming === p.dir
                    ? <NameInput value={p.title} onDone={(n) => void actions.rename(p, n)} onCancel={() => actions.setRenaming(null)} />
                    : <b>{p.title}</b>}
                  <span>{nicheLabel(p.niche)} · {p.created} · {p.runCount} lần xuất</span>
                  <ProjectMenu p={p} actions={actions} />
                </div>
              </div>
            );
          })}
        </div>
      )}
      <DeleteDialog actions={actions} />
    </div>
  );
}
```

(Match `ProjectMenu`/`NameInput` prop names to what Task 4 actually exported.) CSS appended to `styles.css`:

```css
/* ---------- library ---------- */
.lib{padding:24px 28px;overflow-y:auto;height:100%}
.lib h2{margin:0 0 14px;font-size:20px;font-weight:700}
.lib h2 .muted{color:var(--faint);font-weight:600;font-size:14px}
.lib-bar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}
.lib-bar input{flex:1;min-width:180px}
.lib-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px}
.lib-card{cursor:pointer;border-radius:var(--r);padding:6px;transition:background .12s;position:relative}
.lib-card:hover{background:#efeff2}
.lib-thumb{position:relative;aspect-ratio:9/16;border-radius:10px;overflow:hidden;background:var(--sunken);display:grid;place-items:center;color:var(--muted)}
.lib-thumb img{width:100%;height:100%;object-fit:cover;display:block}
.lib-thumb .st{position:absolute;top:8px;right:8px;box-shadow:0 0 0 2px #fff}
.lib-ph{font-size:12px;font-weight:600}
svg.lib-ph{width:28px;height:28px}
.lib-meta{position:relative;padding:8px 26px 2px 2px;font-size:12px;color:var(--muted)}
.lib-meta b{display:block;color:var(--ink);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lib-meta .more{position:absolute;top:6px;right:0}
.lib-empty{display:flex;flex-direction:column;align-items:center;gap:12px;padding:60px 0;color:var(--muted)}
```

Reuse existing input/select styles if the app has them (check `styles.css` for `input`/`select` rules); `.pmenu` positioning must work inside `.lib-meta` (it is `position:relative`).

`App.tsx`: `import Library from "./screens/Library";` and `case "library": return <Library />;`.

- [ ] **Step 4:** `cd app && npx vitest run && npm run build` → PASS.

- [ ] **Step 5: Commit** `feat(app): Thư viện video — thumbnail grid, search/filter/sort, thumb backfill`.
