# Voiceover + Pixel edit quality + basic settings: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship v0.3.0 with:
- per-video ElevenLabs voiceover;
- edit-quality upgrades ported from the `pixel-video-edit` skill;
- a "defaults for new videos" settings card;
- Sonnet 5.5 as the default model.

**Architecture:** There are two tracks that touch disjoint trees.
- **Engine track (`engine/`, `agent/`):** Python. It runs sequentially because the tasks share `edl.py`, `prompt.py` and `tools.py`.
- **App track (`app/`):** Tauri, Rust and React. It runs in parallel with the engine track.

The tracks meet only through the **contract** below: `project.json` keys, `settings.json` keys, env vars and error codes.

**Tech Stack:**
- Python 3.12 (uv, pytest, stdlib `urllib` for HTTP), ffmpeg;
- Rust (Tauri 2, keyring through `SecretStore`, `ureq`/`reqwest`, whichever the crate already uses for license HTTP);
- React + TS (vitest).

**Spec:** `docs/superpowers/specs/2026-11-21-voiceover-and-pixel-design.md`. Read it fully before starting. This plan argues from it.

## Global Constraints
- Branch `feat/voiceover`. Version bump to 0.3.0 happens only in the final task, done by the coordinator.
- **NO real network calls to ElevenLabs or Anthropic, and no live Claude runs.** Use fake HTTP servers and monkeypatching only.
- No deploys and no release builds.
- Never write any API key to a file, log, test fixture, commit or chat. Tests use obviously fake keys such as `"test-key"`.
- Commits end with `Co-Authored-By: <your model> <noreply@anthropic.com>`.
- Commit after each task with a conventional message (`feat(engine): …`, `feat(app): …`).
- User-facing strings are Vietnamese, matching the spec text verbatim where the spec quotes them.
- Old projects (missing new keys) and old `settings.json` must load with defaults.
- Engine test command: `cd engine && uv run pytest -q`.
- App test commands:
  - `cd app && npx vitest run && npx tsc --noEmit`
  - `cd app/src-tauri && cargo test && cargo clippy --all-targets -- -D warnings`
- Keep existing tests green. Update a test only when the spec intentionally changes the behaviour, for example the overlap merge becoming a rejection.

## Contract (engine ⇄ app)

| Item | Value |
|---|---|
| `project.json` `voiceover` | `{"enabled": bool, "voice_id": str, "voice_name": str}` or absent/null |
| `project.json` `product_info` | str, ≤500 chars, default `""` |
| `project.json` `cta_text` | str, 1–30 chars; absent → `"BẤM GIỎ HÀNG 👇"` |
| `project.json` `length` | `"short"` (15–20 s), `"medium"` (20–35 s, default), or `"long"` (35–60 s) |
| Env for `edit` only | `ELEVENLABS_API_KEY` (from Keychain account `elevenlabs`) |
| Engine error codes | `VOICE_AUTH`, `VOICE_QUOTA`, `VOICE_MISSING`, `VOICE_LIMIT`, `VOICE_FAILED` |
| App-only error codes | `ELEVEN_KEY_INVALID`, `ELEVEN_OFFLINE` |
| `settings.json` new keys (camelCase) | `voiceId`, `voiceName`, `defaultLogo` (absolute path or null), `defaultCta` (default "BẤM GIỎ HÀNG 👇"), `defaultLength` (default "medium") |
| Model default | `claude-sonnet-5-5` |
| Model options | `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-haiku-5-5` |

---

# ENGINE TRACK (one agent, tasks E1→E8 in order)

### Task E1: Project fields, model default, length/CTA in the edit prompt

**Files:**
- Modify:
  - `engine/autoedit/project.py` (`_FIELDS`, `Project`)
  - `engine/autoedit/agent/options.py` (`DEFAULT_MODEL`)
  - `engine/autoedit/agent/prompt.py`
  - `engine/autoedit/edl.py` (CTA default from the project)
  - `engine/autoedit/agent/tools.py` (`set_edl` length note)
  - `agent/CLAUDE.md` (replace "Typical result: 15–45 s" wording)
- Test: `engine/tests/test_project_defaults.py` (new), plus additions to `test_edl.py` and `test_prompt*.py`, whichever already exists.

**Interfaces (produced):**
```python
# project.py
LENGTHS = {"short": (15.0, 20.0), "medium": (20.0, 35.0), "long": (35.0, 60.0)}
@dataclass
class Project:
    ...existing...
    voiceover: dict | None = None      # {"enabled","voice_id","voice_name"}
    product_info: str = ""
    cta_text: str = DEFAULT_CTA        # import from edl or move the constant to project.py; avoid an import cycle
    length: str = "medium"
    @property
    def voiceover_on(self) -> bool: return bool(self.voiceover and self.voiceover.get("enabled") and self.voiceover.get("voice_id"))
    @property
    def length_range(self) -> tuple[float, float]: return LENGTHS.get(self.length, LENGTHS["medium"])
```
Add the 4 keys to `_FIELDS`. When loading, sanitize the values:
- an unknown `length` → `"medium"`;
- an empty `cta_text` or one over 30 characters → the default;
- `product_info` is truncated to 500 characters.

**Behaviour:**
- `options.DEFAULT_MODEL = "claude-sonnet-5-5"`.
- `build_edit_prompt` adds two lines: `f"Target length: {lo:.0f}–{hi:.0f}s."` and `f"CTA text: {project.cta_text} (use it unless the customer request asks for another CTA)."`.
- `validate_edl` gains a keyword parameter `default_cta: str = DEFAULT_CTA`. When `cta_text` is missing or blank, it uses `default_cta`. The `set_edl` handler passes `session.project.cta_text`.
- `set_edl` success text appends a note when the output duration `d` is outside `[lo*0.8, hi*1.2]`: `"Lưu ý: video dài {d:.1f}s, mục tiêu {lo:.0f}–{hi:.0f}s — hãy chỉnh lại."`. This is not an error.

- [ ] **Step 1:** Write failing tests:
  - a legacy `project.json` without the new keys loads with the defaults;
  - a bad `length` value falls back to `medium`;
  - the prompt contains `Target length: 20–35s` and the CTA line;
  - `validate_edl` uses `default_cta`;
  - the `set_edl` note appears for a 10 s output on a `medium` project.
- [ ] **Step 2:** Run the tests and confirm they fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full engine suite and make it green.
- [ ] **Step 5:** Commit `feat(engine): project cta/length/voiceover fields, sonnet default, length note`.

### Task E2: Free shot order and hook text without a moved range (spec B2)

**Files:**
- Modify: `engine/autoedit/edl.py`, `agent/CLAUDE.md`
- Test: `engine/tests/test_edl.py`, `test_captions.py`, `test_edl_broll.py`

**Behaviour:**
- `validate_edl` no longer sorts `keep`.
- Ranges overlapping ANY other kept range are rejected. Example error: `"keep[2] (10.0–12.0) chồng lên keep[0] (11.0–13.0); mỗi đoạn chỉ dùng một lần"`. This counts as an EDL error like the other validation errors.
- Ranges that are adjacent in the list AND touching (`a.end` within 0.05 s of `b.start`, same clip) merge.
- `hook`:
  - `{"text": "..."}` without `move_to_front` is valid. The hook text overlays the output from 0 to 2.5 s.
  - With `move_to_front`, the current behaviour is unchanged.
- `Edl.ordered()` returns the list order, with the hook range first when it was moved.
- Check every consumer of `ordered()` and `output_span` for an assumption that ranges are sorted. Look in `render/segments.py`, `captions.py`, `pipeline._broll_inputs`, `tools.py` and `fallback.py`, and fix any you find.
- The speech coverage ≥30% rule is skipped when the caller passes `voiceover_on=True`, a new keyword argument of `validate_edl` with default False.
- `CLAUDE.md`:
  - document that keep order = play order, any order allowed, no overlaps;
  - document that the hook text can be given without `move_to_front`.

- [ ] **Step 1:** Write failing tests:
  - a reversed keep order is preserved;
  - overlap is rejected;
  - list-adjacent touching ranges merge;
  - hook text alone is valid;
  - `map_words` captions are correct for reversed ranges (words keep output-time order);
  - b-roll `at` maps correctly under reversed ranges;
  - the coverage rule is skipped with `voiceover_on=True`.
- [ ] **Step 2:** Run the tests and confirm they fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite and make it green.
- [ ] **Step 5:** Commit `feat(engine): free shot order, hook text without move_to_front`.

### Task E3: Freeze and pop QC (spec B3)

**Files:**
- Modify:
  - `engine/autoedit/render/qc.py`
  - `engine/autoedit/render/pipeline.py` (pass the b-roll windows and cut times)
  - `engine/autoedit/agent/tools.py` (`render_preview` text)
- Test: `engine/tests/test_qc.py` (new or extend)

**Interfaces:**
```python
def detect_freezes(path: Path, noise=0.003, min_dur=0.5) -> list[tuple[float, float]]  # ffmpeg freezedetect; port of ~/.claude/skills/pixel-video-edit/scripts/freeze_check.py
def pop_scores(path: Path, cuts: list[float], sr=48000) -> list[tuple[float, float]]    # (cut_t, score) — max |diff| within ±15 ms / (median |diff| within ±300 ms + 1e-6); numpy if already a dependency, else array module
def run_qc(path, expected_duration, *, broll: list[tuple[float, float]] = (), cuts: list[float] = ()) -> QcReport
```
- Freezes that overlap no b-roll window become the issue `"khung đứng {s:.2f}–{e:.2f}s"`.
- A pop score above 8 becomes the issue `"tiếng bụp ở cắt {t:.2f}s"`.
- `cuts` are the output-time boundaries between consecutive ordered ranges.
- `render_preview` appends `"Kiểm tra: " + "; ".join(issues)` when there are freeze or pop issues. It runs these two checks on the preview file and skips the LUFS check there.

- [ ] **Step 1:** Write failing tests with synthetic media built by ffmpeg `lavfi` in `tmp_path`:
  - `testsrc` for 2 s followed by a 1.5 s still (`tpad=stop_mode=clone`) is flagged;
  - the same still is not flagged when a b-roll window covers it;
  - a sine tone with a sample discontinuity (concat of two sines with a phase jump, or one sample set to 1.0) gives a score above 8 at that cut;
  - a smooth sine gives a score of 8 or below.
- [ ] **Step 2:** Run the tests and confirm they fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite and make it green.
- [ ] **Step 5:** Commit `feat(engine): freeze and pop QC in preview and final`.

### Task E4: Visual-first skill, prompts and suggestion rules (spec B1, B4, C length in suggestions)

**Files:**
- Create: `agent/.claude/skills/visual-first/SKILL.md`. Adapt `~/.claude/skills/pixel-video-edit/references/visual-first-fashion.md`:
  - keep sections (1)–(6) and the 540p self-check;
  - drop the `self_eval.py` mention (the engine QC does this now);
  - state that keep order is free and that hook text needs no moved range;
  - bound the b-roll to the editor's limits (1.5–4 s, at most one per 3 s);
  - no beat-sync promises;
  - keep the frontmatter `name`/`description` like the other skills in `agent/.claude/skills/`.
- Modify:
  - `engine/autoedit/agent/prompt.py`: inject `skill_body("visual-first")`:
    - in full when `not prepared.words`;
    - otherwise a short heading "Khi lời thoại yếu hoặc bật lồng tiếng:" plus the body, only when `project.voiceover_on`.
  - `agent/CLAUDE.md`: replace the no-speech rule with a pointer to visual-first.
  - `engine/autoedit/agent/analyze.py` `INSTRUCTIONS` gains a rule block:
    - one output video, shots in any order (clip numbers only as the shot source);
    - one hook text of at most 5 words in the first 2.5 s;
    - b-roll 1.5–4 s, at most one per 3 s;
    - CTA in the last 2 s;
    - no invented product facts;
    - target length from `project.length_range`;
    - a visual-first hint when there is no speech;
    - voiceover state plus `product_info` when voiceover is on.
- Test: extend `test_analyze.py` and the prompt tests with string-contains assertions. No Claude calls.

- [ ] **Step 1:** Write failing tests:
  - a no-speech prompt contains the visual-first body marker, for example "Dựng theo hình";
  - a speech prompt without voiceover does not contain it;
  - the analyze instructions contain "một video", the length range and the product info when voiceover is on.
- [ ] **Step 2:** Run the tests and confirm they fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite and make it green. Check that `resources.py` or the PyInstaller spec bundles `agent/.claude/skills/*` by glob. If skills are listed explicitly, add the new one.
- [ ] **Step 5:** Commit `feat(engine): visual-first skill, suggestion rules aligned with editor`.

### Task E5: ElevenLabs client (spec A3)

**Files:**
- Create: `engine/autoedit/voice/__init__.py`, `engine/autoedit/voice/eleven.py`
- Modify:
  - `engine/autoedit/errors.py`: add `VoiceAuth` (`VOICE_AUTH`), `VoiceQuota`, `VoiceMissing`, `VoiceLimit`, `VoiceFailed`.
  - `engine/autoedit/secrets_env.py`: add `"ELEVENLABS_API_KEY"` to `SECRET_NAMES`.
- Test: `engine/tests/eleven_fake.py` (a fake HTTP server modelled on `tests/social_fake.py`) and `engine/tests/test_eleven.py`.

**Interfaces:**
```python
MODEL_ID = "eleven_v4"
def quota() -> int                                    # GET /v1/user/subscription → character_limit - character_count
def tts(text: str, voice_id: str, cache_dir: Path) -> tuple[Path, list[tuple[str, float, float]]]
    # cache key sha1(f"{voice_id}|{MODEL_ID}|{text}") → cache_dir/<h>.mp3 + <h>.json (words); hit → no HTTP
    # POST /v1/text-to-speech/{voice_id}/with-timestamps  body {text, model_id, language_code:"vi", output_format:"mp3_44100_128"}
    # header xi-api-key from secrets_env.get("ELEVENLABS_API_KEY") (missing → VoiceAuth); UA f"AutoEdit/{__version__}"; timeout 60
def alignment_to_words(alignment: dict) -> list[tuple[str, float, float]]  # characters/character_start_times_seconds/character_end_times_seconds, split on whitespace
```
- The base URL comes from `os.environ.get("ELEVENLABS_BASE", "https://api.elevenlabs.io")`.
- Error mapping is exactly the spec A3 table, with the Vietnamese messages verbatim.
- Error messages never include the key.

- [ ] **Step 1:** Write failing tests:
  - alignment grouping, including multiple spaces and Vietnamese diacritics;
  - a `tts` round trip against the fake server writes the mp3 and json;
  - a second call is a cache hit (the fake server counts requests);
  - each error status maps to the right class (401, 401 quota_exceeded, 402, 404, 422 voice, 429, 500, connection refused);
  - a missing key raises `VoiceAuth`;
  - `quota()` returns limit minus count.
- [ ] **Step 2:** Run the tests and confirm they fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite and make it green.
- [ ] **Step 5:** Commit `feat(engine): ElevenLabs TTS client with cache`.

### Task E6: `voiceover` agent tool, EDL voiceover, pre-flight, prompt (spec A4)

**Files:**
- Modify:
  - `engine/autoedit/agent/session.py`: `voice_lines: dict[tuple[float, str], VoiceLine]`, `voice_calls: int = 0`.
  - `engine/autoedit/agent/tools.py`: the `voiceover` tool is registered only when `session.project.voiceover_on`. `TOOL_NAMES` stays the base tuple; `build_server` and the allowed-tools list add it conditionally. Check `options.py`/`runner.py` for where allowed tool names are built.
  - `engine/autoedit/edl.py`: `Edl.voiceover: list[VoiceCue]` and its validation.
  - `engine/autoedit/agent/prompt.py`: the voiceover block.
  - `engine/autoedit/agent/runner.py` (or wherever `edit` starts the agent): the pre-flight.
- Test: `engine/tests/test_voiceover_tool.py`. Monkeypatch `eleven.tts` to return a short silent mp3 generated by ffmpeg, plus fake words.

**Interfaces:**
```python
@dataclass
class VoiceLine: at: float; text: str; path: Path; duration: float; words: list[tuple[str, float, float]]
@dataclass
class VoiceCue: at: float; text: str          # in Edl; to_dict → {"at","text"}
def validate_edl(raw, words, clip_duration, image_names, *, default_cta=DEFAULT_CTA, voiceover_on=False,
                 voice_lines: dict | None = None) -> Edl
```
- The tool input is `{lines: [{at, text}]}`.
- Reject the call with no TTS when any line is over 120 characters, the total is over 600 characters, `voice_calls` is already 3, or `at` is not inside a kept range of the current EDL. When there is no EDL yet, accept any `at` inside the timeline.
- Otherwise call `eleven.tts(text, voice_id, project.work_dir / "vo")` per line and probe the duration.
- Return JSON-ish text per line: `{at, text, duration, out_start, out_end}`, where the output window comes from the current EDL. Add warnings for an overlap with the next line (gap below 0.3 s) and for running past the video end.
- `validate_edl` checks the voiceover:
  - each `(at, text)` must be in `voice_lines`;
  - `at` must map to output time;
  - lines must not overlap;
  - no line may end after the output end;
  - lines are sorted by output start.
- Pre-flight: when `voiceover_on`, before any Claude turn, run `eleven.quota() >= 600` or raise `VoiceQuota`.
- A `VoiceAuth`/`VoiceMissing`/`VoiceQuota` raised inside the tool aborts the session with that error. The run must fail with that code, not with `AGENT_FAILED`. Check how the runner propagates errors; for example, set `session.aborted` plus a stored exception, then re-raise after the SDK loop.
- `set_edl` passes `voiceover_on` and `voice_lines`.
- Prompt block, only when voiceover is on:
  - `"Thông tin sản phẩm (khách nhập): " + product_info` (or "(trống)");
  - the rules from spec A4 verbatim in meaning (no invented facts, about 2.5 words per second, 0.3 s gap, the last line is the cart CTA);
  - the instruction to call `voiceover` first and then `set_edl` with `voiceover`.
- Document the tool and the `voiceover` EDL field in `agent/CLAUDE.md` under a "Lồng tiếng (chỉ khi bật)" section.

- [ ] **Step 1:** Write failing tests:
  - the tool is absent when voiceover is off and present when on;
  - each limit returns an error without calling `tts`;
  - a successful call stores the lines;
  - `set_edl` rejects an unknown line, overlaps, and a line past the end;
  - the pre-flight raises `VoiceQuota` at quota 599 before any SDK call (monkeypatch);
  - `VoiceAuth` from the tool propagates as `VOICE_AUTH`.
- [ ] **Step 2:** Run the tests and confirm they fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite and make it green.
- [ ] **Step 5:** Commit `feat(engine): voiceover agent tool, EDL voiceover, quota preflight`.

### Task E7: Render with voiceover (spec A5)

**Files:**
- Modify:
  - `engine/autoedit/render/segments.py`: a `mute: bool` option that applies `volume=0` to segment audio and keeps the fades.
  - `engine/autoedit/render/compose.py`: voiceover inputs mixed with `adelay`, and music ducked under the voiceover intervals.
  - `engine/autoedit/render/captions.py`: `build_voice_cues(cues, lines, fixes, emphasis)`.
  - `engine/autoedit/render/pipeline.py`: wiring. The voiceover file paths come from the cache (`eleven.tts` is a cache hit at render time; it must not call HTTP when the cache exists).
- Test: `engine/tests/test_voice_render.py`.

**Behaviour:**
- When `edl.voiceover` is non-empty:
  - the base audio is muted;
  - each line `i` is mixed at `out_start` with `adelay={ms}|{ms}` and combined with `amix=normalize=0`;
  - music ducks over `[(out_start, out_start + duration)]`;
  - captions come from the voice words at `out_start + word_t`, with the existing `chunk` and style;
  - `caption_fixes`/`emphasis` apply by text match;
  - loudnorm is unchanged.
- At render time, a missing cache file is re-synthesized through `eleven.tts`. That can raise a `Voice*` error, which is fine: never render silently without the voiceover.

- [ ] **Step 1:** Write failing tests with synthetic media and a fake voice mp3, which is a 1 kHz sine of 1 s made with ffmpeg and placed in the cache dir under the right hash:
  - the output RMS in the window `[out_start, out_start+1]` is clearly above the RMS of the muted base elsewhere (use `astats` or numpy over the PCM);
  - the captions ASS contains the voice words at the expected times;
  - the original speech words are absent from the captions.
- [ ] **Step 2:** Run the tests and confirm they fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite and make it green.
- [ ] **Step 5:** Commit `feat(engine): render voiceover mix, ducking and captions`.

### Task E8: Engine wrap-up
- [ ] Re-read the spec A, B and C sections. Verify every engine bullet has a test. Fill the gaps.
- [ ] Also check `fallback.py`, the non-agent path. If voiceover is on and the agent fails, the fallback must not render a video with the original audio muted and no voiceover. It must either keep the original audio (voiceover is skipped, and the summary says so) or fail. Choose: **fail with the original error**. This matches spec A "never silently renders without a voiceover" only when voiceover was intended; document the choice in the commit.
- [ ] Run the full suite and commit.

---

# APP TRACK (one agent, tasks P1→P5 in order; touch only `app/`)

### Task P1: Settings fields, model list and default

**Files:**
- `app/src-tauri/src/settings.rs`: new fields `voice_id: Option<String>`, `voice_name: Option<String>`, `default_logo: Option<String>`, `default_cta: String` (default "BẤM GIỎ HÀNG 👇"), `default_length: String` (default "medium"). The `model` default becomes `"claude-sonnet-5-5"`.
- The `Settings.tsx` `MODELS` list has three entries: Sonnet 5.5 (default, first), Opus 5.5 ("tốt nhất, tốn nhiều lượt nhất") and Haiku 5.5 ("rẻ nhất, dựng kém hơn với clip khó").
- `app/src/lib/types.ts` mirrors the new fields.

**Tests:**
- Rust:
  - an old settings JSON without the new keys loads the defaults;
  - a saved `"claude-opus-5-5"` model is kept;
  - an empty JSON gives Sonnet.
- Vitest: three model options, with Sonnet selected by default.

Commit `feat(app): sonnet default, model list, settings fields`.

### Task P2: ElevenLabs key commands and engine env

**Files:**
- `secrets.rs`: `pub const ELEVEN_ACCOUNT: &str = "elevenlabs";`.
- `commands.rs` / `lib.rs`: add `eleven_status`, `set_eleven_key(key)`, `clear_eleven_key()` and `eleven_voices()` to the license gate's allowed list in `license.rs` exactly like the existing gated commands. Read how `allowed()` works and add tests.
- New module `app/src-tauri/src/eleven.rs`:
  - HTTP client with base URL from an injectable parameter (tests use a local mock server, the same approach the license tests use);
  - `subscription(base, key) -> Result<u64 /*remaining*/, ElevenErr>`;
  - `voices(base, key) -> Vec<Voice{id,name,labels: HashMap<String,String>, preview_url}>`;
  - 401 → `ELEVEN_KEY_INVALID`; a network error → `ELEVEN_OFFLINE`.
  - Return errors in the same shape existing commands use for typed errors. Look at how activation errors are typed.
- `set_eleven_key` validates through `subscription` before storing. `clear_eleven_key` deletes the key and clears `voiceId`/`voiceName` in settings.
- The key is never returned to the UI and never logged.
- `sidecar::engine_env`: push `ELEVENLABS_API_KEY` only when `sub == "edit"`. Add a test asserting it is absent for `social`, `analyze` and `mcp-check`.
- `tauri.conf.json` CSP: add the ElevenLabs preview host to `media-src`, for example `https://storage.googleapis.com` (voice `preview_url`s are hosted there). Keep everything else.

**Tests:**
- fake `SecretStore` key commands;
- mock-server subscription for 200, 401 and connection refused;
- voices parsing;
- `engine_env` least privilege.

Commit `feat(app): ElevenLabs key + voices commands, edit-only env`.

### Task P3: Settings UI, "Lồng tiếng (ElevenLabs)" section and the "Mặc định cho video mới" card

**Files:** `app/src/screens/Settings.tsx` (+ test), `app/src/lib/api.ts`, `app/src/lib/errors.ts` (+ test). Use Rust commands for the logo default:
- `set_default_logo(path)`:
  - validates the extension (png, jpg, jpeg) the same way the existing logo checks do;
  - copies the file to `<app data dir>/defaults/logo.<ext>`, removing any old `logo.*`;
  - stores the absolute path in `default_logo`.
- `clear_default_logo()`.

Both commands are added to the license gate.

**UI:**
- The Lồng tiếng section goes in the `conn` tab, next to SocialSettings:
  - key input plus Lưu;
  - status line "Còn {remaining} ký tự";
  - voice list with name, labels and a ▶ button (an `<audio>` element plays `previewUrl`);
  - "Chọn làm mặc định", which saves `voiceId`/`voiceName`;
  - "Xóa key".
- The defaults card goes in the `gen` tab:
  - logo thumbnail through `convertFileSrc`, "Chọn logo" and "Bỏ logo";
  - CTA input, 1–30 characters, with an inline error otherwise; it saves on blur or on a Lưu button;
  - length radio/chips "Ngắn 15–20s / Vừa 20–35s / Dài 35–60s".
- `errors.ts`: Vietnamese messages for `ELEVEN_KEY_INVALID`, `ELEVEN_OFFLINE`, `VOICE_AUTH`, `VOICE_QUOTA`, `VOICE_MISSING`, `VOICE_LIMIT` and `VOICE_FAILED`. Use the spec A3 messages for the `VOICE_*` codes.

**Tests (vitest, mock `invoke`):**
- the key save path calls `set_eleven_key`;
- the voices list renders, and the default selection saves settings;
- the CTA validation;
- the length save;
- logo set and clear call the commands.

Rust tests:
- `set_default_logo` copies the file into a temp data dir and replaces an old one;
- it rejects `.gif`.

Commit `feat(app): voiceover settings and new-video defaults card`.

### Task P4: Project fields at creation and `set_project_voiceover`

**Files:** `app/src-tauri/src/projects.rs`, `commands.rs`.
- `projects::create` gains `cta_text: &str` and `length: &str`. It validates them: CTA 1–30 characters (trim), else the default; length in the set, else `medium`. It writes the `cta_text` and `length` keys. Update the `create_project` command and its callers.
- `ProjectSummary`/detail exposes `cta_text`, `length`, `voiceover` and `product_info`, read with defaults for old projects.
- `set_project_voiceover(dir, voiceover: Option<{enabled, voice_id, voice_name}>, product_info: String)`:
  - writes under the existing `project.json.lock` the same way `update` does;
  - truncates `product_info` to 500 characters;
  - is added to the license gate.

**Tests:**
- create writes the keys;
- bad values fall back to defaults;
- an old project loads with defaults;
- `set_project_voiceover` writes the keys and holds the lock (follow the existing lock test pattern).

Commit `feat(app): project cta/length/voiceover fields`.

### Task P5: New Video screen and the outline list

**Files:** `app/src/screens/NewVideo.tsx` (+ test).
- The logo slot is pre-filled from `settings.defaultLogo` when it is set. The customer can remove or replace it.
- Length chips are pre-filled from `settings.defaultLength` and passed to `create_project`. The CTA comes from `settings.defaultCta`.
- Toggle "🎙 Lồng tiếng AI":
  - disabled with the link text "Nhập key ở Cài đặt" when `eleven_status.hasKey` is false;
  - disabled with "Chọn giọng mặc định ở Cài đặt" when no `voiceId` is set.
- When the toggle is on, show:
  - a voice dropdown, from `eleven_voices`, defaulting to the settings voice;
  - a textarea "Thông tin sản phẩm" with `maxLength` 500 and a counter.
- On create or build, call `set_project_voiceover`.
- Fix the outline concatenation bug: `<small>{c.outline}</small>` around line 280 becomes `<ol>{c.outline.map(s => <li>{s}</li>)}</ol>`. Handle a string fallback for old cached cards.

**Tests:**
- the toggle disabled states;
- the fields appear when the toggle is on;
- `set_project_voiceover` is called with the chosen voice and info;
- the length chips are pre-filled;
- the logo is pre-filled;
- the outline renders N `li`.

Commit `feat(app): new video voiceover toggle, length chips, outline list`.

---

# COORDINATOR (main session)
1. Review both tracks with an independent reviewer subagent working against the spec. Run a fix wave.
2. Run all suites:
   - `engine`: `uv run pytest -q`
   - `app`: `npx vitest run`, `npx tsc --noEmit`
   - `src-tauri`: `cargo test`, `cargo clippy --all-targets -- -D warnings`
3. Bump to 0.3.0 in the versions: `tauri.conf.json`, `Cargo.toml`, `package.json`, `engine/pyproject.toml`, `autoedit/__init__.py`.
4. Build the dmg only if the user has allowed release builds. The user previously asked for builds, so a local build is OK; no publishing.
5. Report to the user in Vietnamese. Ask for consent before a real ElevenLabs or Claude test on their 2 fashion clips.
