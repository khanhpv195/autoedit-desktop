# Voiceover (ElevenLabs) and Pixel edit-quality upgrades: design

Approved direction 2026-11-21. One release, three parts:

- **A. AI voiceover.** The customer turns it on per video. The engine calls the ElevenLabs API directly; there is no MCP and no `uvx`.
- **B. Edit quality from the `pixel-video-edit` skill:**
  - visual-first editing;
  - free shot order;
  - freeze and pop checks;
  - suggestions that follow the editor's real rules.
- **C. Basic settings and a cheaper default model.**

## Goals and non-goals
Goals:
- Clips without speech get a short Vietnamese voiceover written from the product info the customer typed, with captions synced to each word.
- Fashion clips without speech get edited well: a strong visual hook, good pacing, sensible b-roll, and a hook text.
- The suggestion cards only promise what the editor can do.

Non-goals:
- No automatic beat-sync to music.
- No transitions or speed ramps.
- No subject-aware crop:
  - portrait clips lose almost nothing to a 9:16 cover crop;
  - landscape clips are already fitted over a blurred fill.
- No voice cloning.
- No mixing the voiceover into the original speech. When voiceover is on, the original audio is muted.

---

## A. Voiceover

### A1. Settings: "Lồng tiếng (ElevenLabs)"
- **API key field:**
  - On save, Rust calls `GET https://api.elevenlabs.io/v1/user/subscription` with the header `xi-api-key`.
  - 200 → the key is stored in Keychain (service `AutoEdit`, account `elevenlabs`) and the remaining characters (`character_limit - character_count`) are shown.
  - 401 → `ELEVEN_KEY_INVALID`. A network error → `ELEVEN_OFFLINE`.
  - The key is never written to a file or log and never sent to the UI after it is saved.
- **Voice list:**
  - Loaded with `GET /v1/voices`. Each row shows the name, labels (gender, accent) and a ▶ button that plays `preview_url`.
  - The CSP must allow `media-src` for the ElevenLabs preview storage host.
  - The customer picks a default voice. `settings.json` gets `voiceId` and `voiceName`; neither is secret.
- **"Xóa key"** removes the key from Keychain and clears the default voice.
- **New commands:**
  - `eleven_status` → `{hasKey, remaining?}`
  - `set_eleven_key(key)`
  - `clear_eleven_key()`
  - `eleven_voices()` → `[{id, name, labels, previewUrl}]`
  - All four go through the license gate like every other app command.

### A2. New Video screen
- **Toggle "🎙 Lồng tiếng AI":**
  - Disabled with "Nhập key ở Cài đặt" when there is no key.
  - Also disabled when no default voice is set; the link leads to Settings.
- **When on, two more fields show:**
  - a voice dropdown, defaulting to the Settings voice;
  - a textarea **"Thông tin sản phẩm"** (product name, material, price, offer), up to 500 characters.
- **`project.json` gains:**
  - `voiceover: {enabled: bool, voice_id: str, voice_name: str} | null`
  - `product_info: str` (default `""`)
  - Older projects without these fields load unchanged.
- **Rust:** `set_project_voiceover(dir, voiceover, product_info)` writes under the existing `project.json.lock`.

### A3. Engine: ElevenLabs client (`engine/autoedit/voice/eleven.py`, stdlib only)
- **Request basics:**
  - Base URL from `ELEVENLABS_BASE` (tests) or `https://api.elevenlabs.io`.
  - The key comes from the env var `ELEVENLABS_API_KEY`, set by the app from Keychain through the existing secrets env path. Missing key → `VoiceAuth`.
  - User-Agent `AutoEdit/<version>`, timeout 60 s.
- **`quota() -> int`:** remaining characters, from `/v1/user/subscription`.
- **`tts(text, voice_id) -> (mp3_bytes, words)`:**
  - Calls `POST /v1/text-to-speech/{voice_id}/with-timestamps` with `{text, model_id: "eleven_v4", language_code: "vi", output_format: "mp3_44100_128"}`.
  - It reads `audio_base64` and `alignment` (characters with start and end times) and groups the characters into words, splitting on whitespace. Each word is `(text, start, end)`.
- **Errors map to `AutoeditError` subclasses, each with a Vietnamese message:**

  | Response | Error |
  |---|---|
  | 401, `detail.status` not `quota_exceeded` | `VoiceAuth` "Key ElevenLabs không đúng" |
  | 401 with `detail.status == "quota_exceeded"`, or 402 | `VoiceQuota` "Tài khoản ElevenLabs hết ký tự" |
  | 404 or 422 mentioning the voice | `VoiceMissing` "Giọng đọc không còn trong tài khoản ElevenLabs, chọn giọng khác trong Cài đặt" |
  | 429 | `VoiceLimit` "ElevenLabs đang bận, thử lại sau" |
  | other or network | `VoiceFailed` |

- **Cache:** results are cached in `work/vo/<sha1(voice_id + model + text)>.mp3` plus `.json` (the words). A cache hit never calls the API, so re-rendering or re-editing the same line is free.

### A4. Agent: tool `voiceover`
- **Registration:** the tool exists only when `project.voiceover.enabled`.
- **Input:** `{lines: [{at: number, text: string}]}`.
  - `at` is a timeline second inside a kept range, the same convention as b-roll.
  - Each line is one short sentence, at most 120 characters.
- **Limits:**
  - At most 600 characters per call, counted over new and cached text alike, which keeps the script short.
  - At most 3 calls per session.
  - Over a limit, the tool returns an error and makes no API call.
- **Output:**
  - For each line: the file id, its real duration, and the output-time window after mapping through the current EDL.
  - It also lists problems: lines overlapping the next line, lines running past the video end.
- **The EDL gains `voiceover: [{at, text}]`.**
  - `validate_edl` checks that each `(at, text)` was generated in this session. A cache hit counts as generated.
  - It maps `at` to output time and rejects overlaps and lines past the end.
- **Prompt additions, present only when voiceover is on:**
  - the product info block;
  - "write only what the product info says plus what is visible; no invented material, price, size or promises";
  - "speak about 2.5 words per second; leave 0.3 s between lines; the last line is the cart CTA".
- **Pre-flight before the agent starts:** `quota()` must be ≥ 600, otherwise the run fails with `VoiceQuota` and no Claude turn is spent.

### A5. Render with voiceover
- The original audio of each segment is muted (`volume=0`). The 30 ms fades remain.
- Each voiceover line is placed with `adelay` at its output start, and all lines are mixed with the base.
- Music ducks under the voiceover intervals instead of under the transcript speech.
- **Captions** come from the voiceover words: output time is the line start plus the word time. They use the existing chunking and style. `caption_fixes` and `emphasis` apply to the voiceover words by text match.
- Loudness: two-pass loudnorm to -14 LUFS, unchanged.

---

## B. Edit quality (from `pixel-video-edit`)

### B1. Visual-first skill
- Add `agent/.claude/skills/visual-first/SKILL.md`, adapted from `~/.claude/skills/pixel-video-edit/references/visual-first-fashion.md`.
- Adjust it to our EDL: free order is now allowed, hook text without a moved range, no beat-sync promises.
- It goes in the first message:
  - always when the transcript has no speech;
  - otherwise as a short section "when the speech is weak or voiceover is on".
- `CLAUDE.md`:
  - replace "If the clip has no speech: choose the best visual moments with `view_frames`, `hook: null`" with a pointer to the visual-first skill;
  - document free order;
  - document hook text without a moved range.

### B2. Free shot order
- **`keep`:**
  - Ranges play in the given order. They are no longer sorted.
  - Overlapping ranges are rejected with a clear error instead of being merged.
  - Touching neighbours that are adjacent in the list still merge.
- **`hook`:**
  - `move_to_front` becomes optional.
  - `{text}` alone puts the hook text over the first 2.5 s of whatever plays first.
  - With `move_to_front`, today's behaviour stays.
- `Edl.ordered()` follows the list order; the hook range, when given, still comes first.
- **Captions:** `map_words` already handles ranges that jump backwards (groups). Add tests.
- **B-roll** maps `at` through the ordered ranges, which already works. Add tests for reordered ranges.
- **Speech coverage:** the rule "keep at least 30% of the speech" stays. It is skipped when voiceover is on, because the original audio is muted.
- **Prompts:**
  - The suggestion and edit prompts say that any order of shots is possible.
  - Clips are referred to by number only as the source of a shot.

### B3. Freeze and pop checks
- **`render/qc.py` gains two checks:**
  - `freezedetect=n=0.003:d=0.5`. A freeze that does not overlap a b-roll window is an issue; b-roll images are allowed to be still.
  - A pop score at each cut: the largest sample-to-sample jump within ±15 ms of the cut, divided by the median jump within ±300 ms. Above 8 is an issue. The method is ported from `self_eval.py`.
- `render_preview` runs these checks on the preview and adds a line to its text, for example "Kiểm tra: khung đứng 3.20–4.10s; tiếng bụp ở cắt 12.40s", so the agent can fix them.
- The final render's QC report includes the same checks.

### B4. Suggestions follow the editor's rules
- `analyze.INSTRUCTIONS` gains a compact rule block:
  - one output video;
  - any shot order;
  - one hook text of at most 5 words in the first 2.5 s;
  - b-roll 1.5–4 s, at most one per 3 s;
  - CTA in the last 2 s;
  - no invented product facts.
- It also gains a visual-first hint when there is no speech, and the voiceover state plus product info when voiceover is on.
- UI: the card `outline` renders as a list, one step per line. Today the array is concatenated.

---

## C. Basic settings and model

### C1. Model
- The Settings model list becomes three options:
  - Sonnet 5.5 (`claude-sonnet-5-5`), the **new default**;
  - Opus 5.5 ("tốt nhất, tốn nhiều lượt nhất");
  - Haiku 5.5 (`claude-haiku-5-5`, "rẻ nhất, dựng kém hơn với clip khó").
- The same model is used for editing and for the suggestion cards.
- The default changes to Sonnet 5.5 in `settings.rs` and in the engine's `DEFAULT_MODEL`.
- A saved `model` value in an existing `settings.json` is kept as is. Only the 0.2.x test installs have one.

### C2. "Mặc định cho video mới" (card in Settings → Chung)
`settings.json` gains `defaultLogo`, `defaultCta` and `defaultLength`.

- **Logo mặc định:**
  - The customer picks a PNG or JPG, which goes through the existing logo checks.
  - It is copied to `<data_dir>/defaults/logo.<ext>`, so the default survives if the original file is moved.
  - The card shows a thumbnail and a "Bỏ logo" button.
  - New Video pre-fills the logo slot with it. The customer can still remove or change it for one video, and the project gets its own copy as today.
- **Chữ kêu gọi mặc định:**
  - A text input, 1–30 characters, default "BẤM GIỎ HÀNG 👇".
  - It is stored per project as `project.json` `cta_text`, set at creation.
  - The prompt tells the agent to use it unless the customer's request asks for another CTA.
  - The EDL's `cta_text` defaults to the project value.
- **Độ dài video:**
  - Three options: Ngắn 15–20 s, Vừa 20–35 s (default), Dài 35–60 s.
  - New Video shows the same three chips, pre-filled from the setting, so it can change per video.
  - `project.json` gains `length: "short" | "medium" | "long"` (default `"medium"`).
  - The edit prompt and the suggestion prompt state the target range, replacing "Typical result: 15–45 s".
  - `set_edl` returns a note when the output falls outside the range by more than 20%, so the agent adjusts. It is not an error.
- Older projects without `cta_text` or `length` load with the defaults.

## Data flow (voiceover on)
1. The customer turns on the toggle, picks a voice, types the product info and presses Dựng.
2. The engine runs prep, then the quota pre-flight.
3. The agent decides shots, calls `voiceover` with its lines, reads back the real durations, then calls `set_edl` with `voiceover` and `render_preview`. The preview shows the QC line. The agent finishes.
4. The final render mutes the original audio, mixes the voiceover, ducks the music, builds captions from the voiceover words, applies loudnorm and runs QC.

## Errors
- Every new error has a code and a Vietnamese message in `lib/errors.ts`: `ELEVEN_KEY_INVALID`, `ELEVEN_OFFLINE` (settings), and `VOICE_*` from the engine.
- A voiceover failure during an edit fails the run with that message. It never silently renders without a voiceover.

## Testing
- **Engine:**
  - a fake ElevenLabs HTTP server, like `FakeBundle`, covering `tts` parsing, the alignment-to-words step, the error mapping, the cache and the quota pre-flight;
  - EDL voiceover validation, free order, overlaps rejected, hook text without a range;
  - render: muted original, the voiceover mixed at the right offset (probe the audio energy), captions from the voiceover;
  - QC: a synthetic clip with a frozen tail gets flagged, and a b-roll window is not flagged; pop score on a synthetic click.
- **Rust:** the key commands use a fake secret store; the subscription check uses a local mock server; `set_project_voiceover` takes the lock.
- **UI:** the Settings section (key, voices, preview, default), the New Video toggle states, the outline list, the model options and their default, the defaults card (logo copy and removal, CTA validation, length) and the length chips pre-filled on New Video.
- **Engine (C):** the prompt contains the length range and CTA; the length note from `set_edl`; legacy projects load with defaults.
- **No real ElevenLabs or Claude calls without asking the user.** A final manual test on the user's 2 fashion clips, with consent.

## Rollout
- Version 0.3.0, branch `feat/voiceover`.
- The customer needs an ElevenLabs account and key. The cost is billed to the customer's ElevenLabs account.
