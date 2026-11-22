# Video library (Thư viện video) + sidebar restructure

**Status:** approved in brainstorming 2026-11-22. Branch `feat/app-logo-copyright` (continues the logo/copyright commit).

## Problem
The sidebar lists every project in one flat list. With dozens of videos it grows without bound, has no search,
filter or thumbnails, and the parked batch-edit spec would add a "Lô" section to the same column.

## Decisions
| # | Question | Decision |
|---|---|---|
| 1 | Sidebar shape | Nav + **"Gần đây"** (max 6) + "Xem tất cả →"; full list lives on a new **Thư viện** page. |
| 2 | Library cells | **Real thumbnails**: engine writes `runs/N/thumb.jpg`; old runs are backfilled once. |
| 3 | Multi-select | **Not in this version.** Per-card ⋯ menu (rename, delete) only. |

## 1. UI

### Sidebar (`app/src/components/Sidebar.tsx`)
Top to bottom:
1. Brand (app icon + "AutoEdit") — unchanged.
2. **"Video mới"** button — unchanged (`go({ name: "niche" })`).
3. Nav items (replace the current Video / Lịch đăng segmented toggle):
   - **Thư viện** with the total project count on the right; active when `route.name === "library"`.
   - **Lịch đăng** — same enabled/disabled behaviour as today (disabled + toast when no bundle.social key);
     active when `route.name === "schedule"`.
4. Section label **"GẦN ĐÂY"** then up to **6** projects (`RECENT_MAX = 6`): projects currently building
   (`state.builds[dir]`) first, then the rest in the existing list order (newest first). Each row keeps today's
   behaviour: click opens the project, ⋯ menu with Đổi tên / Xoá…, status dot, "đang dựng…" subtitle.
5. **"Xem tất cả →"** link under the list, shown only when `projects.length > shown`; goes to `library`.
6. Footer unchanged: "N video", Cài đặt, copyright.

Empty state (0 projects): no "GẦN ĐÂY" section.

### Shared pieces
- Rename input (`NameInput`), delete dialog (`ConfirmDelete`) and the ⋯ menu move out of `Sidebar.tsx` into a
  shared module (e.g. `app/src/components/ProjectActions.tsx`) used by both the sidebar and the library page.
  Behaviour is unchanged, including: delete blocked while building, scheduled-posts warning, navigate to `niche`
  if the open project is deleted.

### Library page (`app/src/screens/Library.tsx`, route `{ name: "library" }`)
- Header: "Thư viện video" + "· N video".
- Toolbar:
  - Search box: matches project title, **case- and diacritic-insensitive** (NFD, strip combining marks, `đ→d`).
  - Ngách select: "Tất cả ngách" + each niche present in the list (label via `nicheLabel`).
  - Trạng thái select: Tất cả / Xong (`done`) / Cần xem lại (`needs_review`) / Đang dựng (in `state.builds`) /
    Mới (`new`).
  - Sort select: Mới nhất (default, existing order) / Cũ nhất (reverse) / Tên A–Z (`localeCompare(…, "vi")`).
  - Filter/sort state is local component state (not persisted).
- Grid: `repeat(auto-fill, minmax(150px, 1fr))`; each card:
  - 9:16 thumbnail box: `<img src={fileSrc(thumb)} loading="lazy">` when `thumb` is set; when building →
    "đang dựng…" placeholder; otherwise a Clapperboard/Film icon placeholder.
  - Status dot (same classes as the sidebar), title (one line, ellipsis), "Ngách · created · K lần xuất".
  - ⋯ menu: Đổi tên / Xoá… (shared component). Click/Enter on the card opens `project`.
- Empty states: no projects → "Chưa có video nào" + "Video mới" button; filters match nothing →
  "Không có video khớp bộ lọc" + "Xoá bộ lọc" button.
- On mount: if any project has `runCount > 0 && !thumb`, call `backfillThumbs()` once per app session
  (module-level flag); see section 2.

Startup route stays `niche`. No change to other screens.

## 2. Thumbnails (backend)

### Engine
- New helper `autoedit/render/thumb.py: make_thumb(video: Path, out: Path) -> bool` — ffmpeg via
  `bins.tool_path("ffmpeg")`: seek `t = 1.0` (or `0` if duration < 1.0 s), one frame, scale width 360
  (`scale=360:-2`), JPEG quality `-q:v 4`, written atomically (temp file + rename). Returns False on any error
  (logs to stderr); never raises.
- `cli.py _edit`: after `_render_with_retry` succeeds and before the run record is written, call
  `make_thumb(res.path, run_dir / "thumb.jpg")`. Failure is ignored.
- New subcommand `autoedit thumbs --root <projects root>`: for each project dir under root with a readable
  `project.json`, take the last run; if `runs/N/final.mp4` exists and `runs/N/thumb.jpg` does not, make it.
  Emits one progress/event per project made (existing Emitter), then done. Projects that fail are skipped.

### Rust (`app/src-tauri/src/projects.rs`, `commands.rs`)
- `ProjectSummary` gains `thumb: Option<String>` (serialized `thumb`): absolute path of the **last run's**
  `runs/<n>/thumb.jpg`, `Some` only if the file exists. Computed in `summary()`.
- No new Rust command: the frontend runs `autoedit thumbs --root <projects root>` through the existing generic
  `engine_run` (`runEngine`), refreshing the project list on each `thumb` event and when the job ends.
  Errors are ignored (logged by the engine), never shown to the user.

### Frontend types/api
- `ProjectSummary.thumb?: string | null` in `app/src/lib/types.ts`.
- `backfillThumbs(root, onThumb)` in `lib/engine.ts`.
- Route type gains `{ name: "library" }`; `App.tsx` renders `<Library />`.

## 3. Testing
- **pytest**: `make_thumb` writes a JPEG for a short generated clip; returns False (no raise) for a missing/corrupt
  input; sub-1 s clip still produces a thumb. `thumbs` command skips projects that already have a thumb and
  projects with no runs. `_edit` still records the run when `make_thumb` fails.
- **cargo test**: `summary().thumb` is `Some(path)` when the last run's `thumb.jpg` exists, `None` otherwise,
  and uses the *last* run.
- **vitest**:
  - Sidebar: shows at most 6 recent projects; building projects come first; "Xem tất cả" appears only when there
    are more; "Thư viện" nav goes to `library`; existing rename/delete tests keep passing.
  - Library: diacritic-insensitive search ("vay" finds "Váy hoa"); niche and status filters; sort options;
    both empty states; thumbnail `img` uses `fileSrc(thumb)`; placeholder when no thumb; backfill called once
    when some project lacks a thumb.

## Out of scope
Multi-select / bulk delete, persisting filters, batch-edit ("Lô") UI, changing the startup screen.
