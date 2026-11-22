# Project names, delete, free duration, chat with the agent

Approved 2026-11-22.

## 1. Project management
- `project.json` gains `name` (1–80 chars, trimmed). Set on create (New video screen, prefilled with the first
  clip's stem), editable later. Lists, sidebar and ProjectView show `name`; a project without one shows its folder
  name minus the date prefix. The folder name never changes (internal id).
- `rename_project(dir, name)`: under the project lock; empty / >80 chars rejected.
- `delete_project(dir)`: removes the whole project folder: input copies, work (cache, transcript, temp renders)
  and exported runs (final.mp4). The customer's original files live outside the folder and are never touched.
  Refused when: dir is not a direct child of the projects root or has no project.json; an engine job runs on it;
  it has a post still waiting to publish (status not published / failed).
- UI: `⋯` menu per project in the sidebar → "Đổi tên" (inline) and "Xoá…" (in-app confirm dialog stating the
  number of exported videos that go with it). ProjectView title is click-to-rename.

## 2. Duration
- `length` (short/medium/long), `LENGTHS`, Settings `defaultLength` and the length chips are removed. Old
  projects' `length` is ignored.
- `autoedit.duration.parse_duration(text) -> (lo, hi) | None`:
  exact ("30s", "30 giây", "cắt còn 30s") ±10%; approximate ("khoảng / tầm / chừng / cỡ / ~") ±15%;
  "1p30", "1 phút 30" = 90 s; ranges "30-45s"; "dưới / tối đa X" → (0.6X, X); "trên / ít nhất X" → (X, 1.4X).
- project.json `target_seconds` ([lo, hi] or null) is written when an edit starts from a chat plan.
  Priority: target_seconds, then parse_duration(prompt), else no target.
- No target: the agent chooses from the speech length, number of key points and the platform, and states the
  chosen length and why in its plan / summary. The full-speech rule still wins over any target.

## 3. Chat instead of the one-shot prompt
- Engine `autoedit chat --project D --message-file F` (one turn; empty message = opening turn). Reads
  `<project>/chat.json`, transcript, niche library; calls Claude (no tools, JSON schema) with the whole history.
  Reply: `{reply, suggestions[], plan|null}`; plan = `{summary, prompt, target_seconds|null, length_reason,
  hook, cta}`. Both messages are appended to chat.json atomically. The existing rules (hook never covers a face,
  CTA bottom-left, captions, no invented product facts, full-speech card) are in the chat system prompt.
- UI: panel 3 of the New video screen becomes a chat: bubbles, quick-reply chips, plan card with
  "Bắt đầu edit" (only on the latest plan), typing indicator with Stop, textarea (Enter sends, Shift+Enter newline).
  The opening turn is sent automatically once clips are in. "Dựng video" is removed: only "Bắt đầu edit" starts
  an edit (saves prompt + target_seconds, then the existing edit flow).
- History persists per project and is deleted with it. ProjectView feedback stays as is.

## Tests
- engine: test_duration.py (table), test_chat.py (fake Claude: history round-trip, plan parsing, bad JSON).
- Rust: rename (empty, too long, old project), delete (outside root, not a project, pending post, ok).
- UI: ChatPanel (send, plan button only on latest plan), Sidebar rename/delete confirm.
