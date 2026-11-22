# Batch edit (Edit hàng loạt)

**Status: DRAFT, parked 2026-11-22.** Decisions below were agreed in brainstorming; section 1 (UI) was shown as a
clickable prototype; sections 2–5 were written up but not yet reviewed section by section. Open questions at the end.
Do not start implementation until the user re-opens and approves this spec.

Prototype: `docs/superpowers/specs/2026-11-22-batch-edit-prototype.html` (open in a browser; also published at
https://claude.ai/artifact/WpffRjMM9DA1JuQFKNsP9K, private).

## Goal
The user gives the app a list of scripts (kịch bản); the app edits one video per script, one after another, with no
questions asked, so a whole batch can run unattended (e.g. overnight).

## Decisions (agreed)
| # | Question | Decision |
|---|---|---|
| 1 | Scripts vs footage | **Each script has its own clips.** One row = one independent video = one normal project. No shared footage pool. |
| 2 | How the list gets in | **Table inside the app** (add/remove rows, pick/drop clips per row). CSV import is a later add-on that fills the same table. |
| 3 | Per-row or shared options | **Shared for the whole batch**: niche, reference template, logo, music, voiceover on/off + voice. Per-row differences are written into that row's script for the AI to follow. |
| 4 | Run and failure policy | **Sequential, one video at a time. A failed video is marked and skipped**, the batch goes on. **Claude rate limit (and auth loss) pauses the whole batch** — later videos would fail too. Pause / Resume / Cancel / Retry failed. |
| 5 | Architecture | **Queue lives in the app (Rust); engine stays as is.** Each row runs the existing `create_project` → `autoedit edit --project D --prompt SCRIPT` path. |

Rejected: a new `autoedit batch` engine command (one long-lived Python process; harder resume and per-video cancel),
and one agent session for all scripts (context bloat, cross-talk between videos, one failure kills the session).
Running 2–3 in parallel was rejected for v1 (CPU from whisper/ffmpeg, Claude quota drains faster, Windows hangs).

## 1. UI (shown in prototype)
- Sidebar: new button **"Edit hàng loạt"** under "Video mới"; a **"Lô"** section lists batches with `done/total`
  and state. Projects created by a batch appear in the normal project list with a small batch-name tag.
- **New batch screen**
  - "Cài đặt chung cho lô": batch name, niche, reference template, logo, music, voiceover toggle (+ voice).
    Defaults come from Settings, same as the New video screen.
  - Script table, one row per video: clips (pick or drop, shows count + total duration), script (multi-line),
    optional video name (empty → "`<batch name>` – #N"), delete row. "+ Thêm dòng" below.
  - Footer: "N video · ước tính ~M phút" and **"Bắt đầu lô"**. A row with clips but no script, or a script but no
    clips, is outlined red and blocks start. Fully empty rows are ignored.
  - Voiceover on → in-app confirm dialog before starting: "N video × lồng tiếng sẽ tốn credit ElevenLabs", with
    estimated characters and remaining quota.
- **Batch screen** (running or finished)
  - Header: Pause / Resume / Cancel batch / "Chạy lại N video lỗi".
  - Summary: counts (xong / cần xem lại / lỗi / còn lại) and an overall progress bar.
  - One line per video: status **Chờ / Đang dựng (step + progress) / ✓ Xong / Cần xem lại / Lỗi + reason / Đã huỷ**.
    Finished videos get a thumbnail and "Mở video" → the normal ProjectView (rebuild with feedback, save as
    template, publish all work unchanged). Failed videos get "Sửa dòng" (change clips/script, then retry).
  - Rate-limit banner: "Hết lượt Claude, lô đã tạm dừng… Bấm Tiếp tục khi có lượt lại."
- "Cần xem lại" = the run record has `fallback: true` (agent failed, silence-cut fallback used) or
  `needs_review: true`. Both already exist in the engine's run record.
- Deleting a batch deletes only the batch record; its projects and videos stay.

## 2. Batch data (draft, not reviewed)
`<data dir>/batches/<id>.json`, written atomically (temp + rename), one file per batch:
```json
{
  "id": "b_20261122_ab12", "name": "Lô váy tháng 11", "created": "2026-11-22T19:30:00+07:00",
  "state": "running",            // idle | running | paused | rate_limited | done | cancelled
  "shared": { "niche": "fashion", "reference": "clip-chuan", "logo": "...", "music": null,
              "voiceover": false, "voice": null },
  "rows": [
    { "n": 1, "name": "Váy hoa – giá sốc", "clips": ["/abs/a.mov", "/abs/b.mov"], "script": "...",
      "status": "wait",          // wait | running | done | review | failed | cancelled
      "project": null,           // project dir once created
      "error": null }            // { "code": "BAD_INPUT", "message": "..." }
  ]
}
```
- Batch stores **original clip paths**; the project copy happens when that row starts (so a 20-row batch does not
  copy 20 × GB up front). If an original is gone at start time → row `failed` with BAD_INPUT, batch continues.
- Project gets `batch: { id, n }` in project.json for the sidebar tag.

## 3. Queue runner (Rust, draft, not reviewed)
- New module `app/src-tauri/src/batch.rs`: a single runner thread per app; at most one batch runs at a time,
  others wait in FIFO.
- Per row: `projects::create(...)` with shared options → `spawn_job(["edit","--project",D,"--prompt",script])`
  (same env as `engine_run`) → forward `engine-event` to the UI tagged with batch id + row → on `Exit` read the
  last error event / run record and set row status.
- Mapping exit → row status:
  - success, run record `fallback` or `needs_review` → `review`; otherwise `done`.
  - `RATE_LIMIT`, `NO_AUTH`, `SETUP_REQUIRED`, `VOICE_QUOTA`, `VOICE_AUTH` → row back to `wait`, batch
    `rate_limited`/`paused` (whole batch stops; resume reruns that row from scratch).
  - any other error (`BAD_INPUT`, `RENDER_FAILED`, `AGENT_FAILED`, `VOICE_FAILED`, …) → row `failed`, next row.
- Pause = finish the current video, then stop. Cancel = `sidecar::cancel` the current job, mark it and all waiting
  rows `cancelled`. A cancelled row's half-made project keeps its input copy but has no run.
- App quit/crash: on start, a batch found in `running` is set to `paused`; its `running` row goes back to `wait`
  (the engine already creates a fresh `runs/N` per edit, so a rerun is safe). User presses Resume.
- Mac sleep: not handled in v1 (see open questions).
- A single edit started by hand while a batch runs: allowed? (open question; default: the manual edit waits).

## 4. Engine changes (draft, not reviewed)
- None required for v1: `edit` already prepares clips, never asks the user, and has error codes.
- Prompt nudge only: in `build_edit_message`, when the project has `batch`, add one line telling the agent that
  nobody will answer questions, so it must decide missing details itself and state them in the summary.
- Optional later: run `prep` for the next row while the agent works on the current one (CPU vs speed trade-off).

## 5. Testing (draft, not reviewed)
- Rust unit tests for `batch.rs` with a fake engine command (script that prints events and exits with a given
  code): ordering, skip on failure, pause on RATE_LIMIT, cancel, resume after restart, atomic file writes.
- React tests (vitest) for the New batch screen validation and the Batch screen states, with `api` mocked like the
  existing screen tests.
- One manual end-to-end run with 3 real rows (one with a broken clip) on Mac and Windows.

## Open questions (to research before re-opening)
1. Claude Pro/Max quota: how many edits per 5-hour window in practice? Decides whether to show an estimate
   ("lô này có thể bị dừng giữa chừng") before start.
2. Should the batch keep the Mac awake (caffeinate / Windows `SetThreadExecutionState`) while running?
3. Manual edit while a batch runs: block, queue, or run in parallel?
4. Max rows per batch (e.g. 50) and disk-space check before start (input copies + renders).
5. Should a batch support auto-publish to bundle.social after each video, or stay edit-only in v1? (Default:
   edit-only.)
6. CSV import column format, if/when added.
