# Multi-clip + images, manual "AI gợi ý" — plan (v0.2.1)

Approved by the user 2026-11-21. Images are used as **b-roll overlays while speech continues** (not standalone slides).

## Contract between engine and app

### project.json
- New fields: `clips: [str]` (ordered, >=1, file names inside `<project>/input/`), `images: [str]` (0..20, file names in `input/`).
- Legacy field `clip: str` (old projects): readers treat it as `clips: [clip]` when `clips` is missing. Writers (Rust) write `clips`/`images` and remove `clip`.
- `logo`, `music`, `prompt`, `script_card`, `runs`, `posts` unchanged.
- Limits: 1..10 clips, 0..20 images, total clip duration <= 600 s (engine enforces with BadInput; UI caps counts).
- Accepted types: clips mp4/mov/m4v; images png/jpg/jpeg/webp.

### Engine CLI
- `analyze --project` and `edit --project` unchanged on the command line. `analyze` is now only launched when the user presses the button.
- Prepare: normalize each clip (cached per clip), then concat in order into one timeline `work/source.mp4` (single clip: use its normalized file directly). Transcript, keyframes, EDL ranges are all in **timeline seconds**. The prompt tells the agent each clip's span, e.g. `Clip 1 "a.mp4": 0.00-12.40s`.
- EDL gets optional `broll: [{image: "<file name from images>", at: <timeline seconds>, dur: 1.5..4.0}]`. `at` must lie inside a kept range; render maps it to output time and overlays the image full-frame (9:16 cover crop, slow 1.0->1.06 zoom), under captions (subtitles stay LAST), never covering the hook's first HOOK_SECONDS. Agent sees each image (downscaled) in the first message, labelled with its file name.

### Rust commands (app)
- `create_project(niche, clips: Vec<String>, images: Vec<String>, logo, music)` — absolute paths, copied into `input/`.
- New `set_project_media(dir, clips: Vec<String>, images: Vec<String>) -> ProjectDetail` — absolute paths in desired order; a path already inside `<dir>/input/` is kept by name, others are copied in (unique names). Unreferenced input files are left on disk. Clears `script_card` only if clips changed? No — leaves it.
- `ProjectDetail.clips: string[]`, `ProjectDetail.images: string[]` (absolute paths) replace `clip`.

### UI (NewVideo)
- One drop zone accepting many files at once (drag-drop and picker with multiple selection), videos and images sorted into a reorderable clip list (↑/↓, ✕) and an image strip (✕), plus "+ Thêm file".
- Project is created when the first clip is added (images added before are held and passed to create). Later changes call `set_project_media`.
- No auto-analyze. Button "✨ AI gợi ý kịch bản" (enabled with >=1 clip, not analyzing); after cards exist, "↻ Gợi ý khác". Changing media clears shown cards.
- Build needs >=1 clip and (prompt or picked card), as before.
