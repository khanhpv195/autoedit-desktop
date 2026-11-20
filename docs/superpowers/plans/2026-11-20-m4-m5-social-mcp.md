# M4 + M5 — Đăng bài bundle.social, khách tự thêm MCP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- **M4 (v2):** khách dán key bundle.social, thấy team/quota/kênh, đăng `final.mp4` ngay / chọn giờ / vào hàng đợi với caption AI viết, xem tab Lịch đăng, đặt routine "mỗi ngày HH:MM đăng video mới nhất chưa đăng".
- **M5 (v3):** khách thêm MCP server của mình (stdio hoặc HTTP) trong Cài đặt; agent dựng dùng được tool của các server đó.

**Architecture:** Mọi lời gọi bundle.social nằm trong engine (`engine/autoedit/social/`, chỉ dùng `urllib` thư viện chuẩn), gọi qua lệnh `autoedit social <lệnh>` và trả event JSON-lines như M1. Rust chỉ thêm secret (key bundle.social, secret của MCP) và truyền vào env khi spawn engine. Routine là hàm Python thuần, chạy `autoedit social routine-sync` mỗi lần mở app. MCP: app lưu cấu hình (không có secret) ở `<app data>/mcp.json`, secret ở Keychain; Rust ghép thành JSON truyền vào engine qua env `AUTOEDIT_MCP` (chỉ trong env của process con); engine thêm vào `mcp_servers` của agent dựng và cho phép `mcp__<tên>`.

**Tech Stack:** như M2 (Tauri 2, React, Rust, Python 3.12/uv). Thêm: package `mcp` (đã có sẵn trong lock, phụ thuộc của claude-agent-sdk) cho `mcp-check`.

**Spec:** `docs/superpowers/specs/2026-11-20-tiktok-autoedit-design.md` mục 7 (bundle.social), mục 1 phân kỳ v3. API: `docs/superpowers/refs/bundle-social-api.md` (trích từ swagger chính thức). Plan M2: `docs/superpowers/plans/2026-11-20-m2-m3-app.md` (Contract M2 vẫn giữ nguyên).

## Global Constraints

- Mọi ràng buộc chung của plan M2 vẫn áp dụng (không lộ secret, tiếng Việt, mã thoát engine, `DISABLE_AUTOUPDATER=1`, màu theo prototype).
- Key bundle.social: Keychain service `AutoEdit`, account `bundle-social-key`; truyền vào engine bằng env `BUNDLE_SOCIAL_KEY`; header HTTP `x-api-key`; base `https://api.bundle.social` (env `BUNDLE_SOCIAL_BASE` chỉ dùng cho test).
- Engine KHÔNG gọi API xóa post, xóa upload, ngắt kênh, xóa team (spec mục 7). Chỉ dùng: `GET /api/v1/organization/`, `GET /api/v1/organization/usage/posts`, `GET /api/v1/organization/usage/uploads`, `GET /api/v1/team/`, `GET /api/v1/team/{id}`, `POST /api/v1/social-account/create-portal-link`, `POST /api/v1/upload/`, `POST /api/v1/upload/init`, `POST /api/v1/upload/finalize`, `POST /api/v1/post/`, `GET /api/v1/post/`, `GET /api/v1/post/{id}`, `POST /api/v1/post/{id}/retry`.
- Kênh hỗ trợ đăng video ở v2: `TIKTOK`, `INSTAGRAM`, `YOUTUBE`, `FACEBOOK`. Nhãn: TikTok, Instagram, YouTube Shorts, Facebook Reels.
- Mã lỗi mới: `SOCIAL_AUTH` (401/403, key sai), `SOCIAL_LIMIT` (429 hoặc hết quota), `SOCIAL_FAILED` (khác). Mã thoát 1.
- File > 90 MB dùng `upload/init` → PUT lên `url` → `upload/finalize`; nhỏ hơn dùng multipart `POST /api/v1/upload/`.
- Không chạy API bundle.social thật trong test hay khi làm task (không có key test). Mọi test dùng server giả cục bộ (`http.server` trên `127.0.0.1` cổng ngẫu nhiên) qua `BUNDLE_SOCIAL_BASE`.
- Thời gian: lưu và gửi API dạng ISO 8601 có múi giờ; UI hiện giờ địa phương.
- MCP: tên server khớp `^[a-z0-9][a-z0-9-]{0,30}$`, khác `autoedit`. Tối đa 10 server. Secret (giá trị env của stdio, giá trị header của HTTP) chỉ nằm trong Keychain account `mcp:<tên>:<khóa>`; `mcp.json` chỉ lưu tên khóa. Chỉ agent `edit` dùng MCP của khách, `analyze` và `auth-check` không.

## Contract mở rộng

### Lệnh engine (qua `engine_run` sẵn có)

| Lệnh | Event cuối |
|---|---|
| `social check` | `{"type":"social_account","organization":{"name"},"usage":{"posts":{"used","limit","remaining"},"uploads":{"used","limit","remaining"}},"teams":[{"id","name","channels":[{"type","name","avatar","username"}]}]}` |
| `social portal --team T` | `{"type":"social_portal","url":"…"}` |
| `social caption --project D --run N` | `{"type":"caption","text":"…"}` (một lượt `query()` không tool, như analyze) |
| `social publish --project D --run N --team T --channel TIKTOK [--channel …] --caption C --when now\|queue\|<ISO>` | `{"type":"social_post","post":Post}`; có `step` khi upload ("Đang tải video lên… N%") |
| `social list --team T --from ISO --to ISO` | `{"type":"social_posts","posts":[Post…]}` |
| `social retry --post ID` | `{"type":"social_post","post":Post}` |
| `social routine-sync --team T` | `{"type":"routine_sync","created":[Post…],"skipped":"…"\|null}` |
| `mcp-check --name X` | `{"type":"mcp_tools","name":"X","tools":[{"name","description"}]}` |

`Post = {"id","title","status","postDate","channels":[TYPE…],"error":str|null,"project":dir|null,"run":int|null,"permalinks":{TYPE:url}}` — `status` là trạng thái bundle.social (`SCHEDULED`, `POSTED`, `ERROR`, `PROCESSING`, …). `project`/`run` lấy từ `referenceKey` dạng `autoedit:<tên thư mục project>:<run>`.

`--when queue`: giờ = slot routine kế tiếp còn trống (theo `AUTOEDIT_ROUTINES`), nếu không có routine thì 19:30 ngày mai (giờ máy).

Routine truyền bằng env `AUTOEDIT_ROUTINES` (JSON `[{"id","time":"HH:MM","channels":[…],"enabled":bool}]`) và thư mục project bằng env `AUTOEDIT_PROJECTS_ROOT` — Rust set cả hai từ settings mỗi lần spawn.

Mỗi lần đăng thành công, engine ghi vào `project.json` khóa `posts` (thêm vào `_FIELDS` của `Project`): `[{"id","run","postDate","channels","status"}]`.

### Command Tauri mới

| Command | Tham số | Trả về |
|---|---|---|
| `social_key_status` | — | `{ hasKey: boolean }` |
| `set_social_key` | `key: string` | `null` |
| `clear_social_key` | — | `null` |
| `mcp_list` | — | `McpServer[]` |
| `mcp_save` | `server: McpServer, secrets: Record<string,string>` | `null` (secret rỗng = giữ giá trị cũ) |
| `mcp_delete` | `name: string` | `null` (xóa cả secret) |

```ts
type McpServer = { name: string; enabled: boolean; transport: "stdio" | "http";
  command?: string; args?: string[]; envKeys?: string[];   // stdio
  url?: string; headerKeys?: string[] };                    // http
type Routine = { id: string; time: string /* HH:MM */; channels: string[]; enabled: boolean };
// Settings thêm: socialTeamId: string | null; routines: Routine[]
```

`engine_env` thêm: `BUNDLE_SOCIAL_KEY` (nếu có), `AUTOEDIT_ROUTINES`, `AUTOEDIT_PROJECTS_ROOT`, `AUTOEDIT_MCP` = JSON `{"<tên>": {"type":"stdio","command","args","env":{k:v}} | {"type":"http","url","headers":{k:v}}}` chỉ gồm server `enabled`, secret điền từ Keychain.

## File Structure

```
engine/autoedit/social/__init__.py
engine/autoedit/social/client.py     # HTTP: x-api-key, map lỗi, upload nhỏ/lớn
engine/autoedit/social/posts.py      # Post chuẩn hóa, referenceKey, queue slot
engine/autoedit/social/routine.py    # plan_routine(now, routines, videos, existing) thuần
engine/autoedit/social/caption.py    # caption AI một lượt
engine/autoedit/social/commands.py   # các lệnh `social …`
engine/autoedit/mcp_user.py          # đọc AUTOEDIT_MCP, mcp-check
engine/tests/social_fake.py          # server bundle.social giả
app/src-tauri/src/mcp.rs             # mcp.json + secret
app/src/screens/Schedule.tsx  components/PostCard.tsx  components/SocialSettings.tsx  components/McpSettings.tsx  components/RoutineEditor.tsx
```

---

### Task 1: Engine — client bundle.social

**Files:** Create `engine/autoedit/social/{__init__,client,posts}.py`, `engine/tests/social_fake.py`, `engine/tests/test_social_client.py`. Modify `engine/autoedit/errors.py` (thêm `SocialAuth` `SOCIAL_AUTH`, `SocialLimit` `SOCIAL_LIMIT`, `SocialFailed` `SOCIAL_FAILED`).

**Interfaces:**
- `client.Client(key: str | None = None, base: str | None = None)` (mặc định env `BUNDLE_SOCIAL_KEY`, `BUNDLE_SOCIAL_BASE` hoặc `https://api.bundle.social`; thiếu key → `SocialAuth("Chưa nhập key bundle.social")`). Methods: `organization()`, `usage_posts()`, `usage_uploads()`, `teams() -> list[dict]` (theo trang `offset/limit=50` tới hết), `team(id)`, `portal_link(team_id, types: list[str]) -> str` (body `{"teamId","socialAccountTypes":types,"language":"en"}`; bundle.social chưa có tiếng Việt), `upload(team_id, path: Path, on_progress=None) -> str` (id upload), `create_post(body: dict) -> dict`, `list_posts(team_id, start: str, end: str) -> list[dict]` (lọc phía client theo `postDate` nếu API không có tham số ngày; đọc tham số thật trong `refs/bundle-social-api.md`), `get_post(id)`, `retry_post(id)`.
- Lỗi: 401/403 → `SocialAuth("Key bundle.social không đúng hoặc đã bị thu hồi")`; 429 → `SocialLimit("bundle.social đang giới hạn, thử lại sau")`; lỗi khác/không kết nối → `SocialFailed(<message từ JSON body nếu có>)`. Timeout 60 s (upload 15 phút).
- Upload nhỏ: multipart tự dựng (boundary ngẫu nhiên, field `teamId`, `file` có `filename` + `Content-Type: video/mp4`), stream file theo khối, không đọc cả file vào RAM nếu > 20MB (dùng iterator body với `Content-Length` tính trước).
- Upload lớn (> 90 MB = `90 * 1024 * 1024`): `init` (`fileName`, `mimeType: "video/mp4"`, `fileSize`) → `PUT url` (không gửi `x-api-key` tới URL ký sẵn) → `finalize {"teamId","path"}`.
- `posts.normalize(raw: dict) -> dict` ra `Post` của Contract; `posts.reference_key(project_dir: Path, run: int) -> str`; `posts.parse_reference(key) -> (dir_name, run) | None`.
- `social_fake.FakeBundle` — context manager chạy `ThreadingHTTPServer` trên `127.0.0.1:0`, lưu các request đã nhận (method, path, headers, body), trả JSON theo bảng route có thể chỉnh trong test (gồm route trả 401/429), và route PUT cho URL ký sẵn.

- [ ] **Step 1: Test** `test_social_client.py` (dùng `FakeBundle`, `monkeypatch.setenv("BUNDLE_SOCIAL_BASE", fake.url)`): header `x-api-key` được gửi; 401 → `SocialAuth`; 429 → `SocialLimit`; 500 có body `{"message":"boom"}` → `SocialFailed` chứa "boom"; `teams()` gộp 2 trang; upload file 1 MB → request multipart có `name="teamId"` và `filename=`; upload với ngưỡng nhỏ (monkeypatch `LARGE = 1000`) → gọi init, PUT (không có `x-api-key`), finalize; `normalize` lấy `referenceKey` ra project/run; không có hàm/route xóa nào trong `client.py` (test `assert "delete" not in inspect.getsource(client).lower()` — trừ chữ trong comment thì đặt comment khác từ).
- [ ] **Step 2–4:** FAIL → cài đặt → `uv run pytest -q -W error` PASS.
- [ ] **Step 5:** Commit `feat(engine): bundle.social REST client (no delete calls), small and large uploads`.

### Task 2: Engine — lệnh `social` và caption

**Files:** Create `engine/autoedit/social/{caption,commands}.py`, `engine/tests/test_social_commands.py`. Modify `engine/autoedit/cli.py` (subparser `social` với các lệnh con), `engine/autoedit/events.py` (thêm `emit_raw(obj)` cho event social), `engine/autoedit/project.py` (`posts: list[dict]` vào dataclass và `_FIELDS`).

**Interfaces:**
- `commands.check(events)`, `portal(events, team)`, `caption(events, project_dir, run)`, `publish(events, project_dir, run, team, channels, caption, when, now=None)`, `list_(events, team, start, end)`, `retry(events, post_id)` — đúng event của Contract.
- `publish`:
  - kiểm `run` có trong `project.runs` và `final.mp4` tồn tại, channels ⊂ 4 kênh v2, caption ≤ 2200 ký tự, nếu không → `BadInput`.
  - `postDate`: `now` → giờ hiện tại + 1 phút; ISO → dùng nguyên (phải ở tương lai, nếu không → `BadInput("Giờ đăng đã qua")`); `queue` → `posts.next_queue_slot(now, routines, existing_post_dates)`.
  - upload → body `{"teamId", "title": <80 ký tự đầu caption>, "referenceKey", "postDate", "status":"SCHEDULED", "socialAccountTypes": channels, "data": {TIKTOK: {"text": caption, "uploadIds":[id], "privacy":"PUBLIC_TO_EVERYONE"}, INSTAGRAM: {"type":"REEL","text":caption,"uploadIds":[id]}, YOUTUBE: {"type":"SHORT","text": caption, "uploadIds":[id]}, FACEBOOK: {"type":"REEL","text":caption,"uploadIds":[id]}}` chỉ gồm kênh được chọn. **Trước khi viết, đối chiếu từng trường (`privacy`, `type`, tên `text`/`description`/`title` của YouTube…) với schema `POST /api/v1/post/` trong `refs/bundle-social-api.md`, sửa body cho khớp schema thật; test phải kiểm body theo schema đó.**
  - ghi `project.posts` rồi `project.save()`.
- `caption`: `query()` một lượt (dùng `plain_options` như `analyze`), đầu vào: ngành, `summary` của run, transcript (text các phrase), hook; yêu cầu: tiếng Việt, ≤ 300 ký tự, 1–2 câu + CTA ngắn + 3–5 hashtag, không hứa hẹn quá đà (luật ở `agent/CLAUDE.md`); ném `RateLimited`/`NoAuth` như analyze. `query_fn` inject được để test.
- CLI: `autoedit social check|portal|caption|publish|list|retry|routine-sync …` (routine-sync cài ở Task 3, ở đây chỉ đăng ký subparser khi Task 3 làm).

- [ ] **Step 1: Test** (FakeBundle + project tạm có `runs/1/final.mp4` nhỏ tạo bằng `bytes`): `check` gộp org + usage + teams (channels từ `socialAccounts` của `team(id)`); `publish --when now` gửi đúng body và ghi `posts` vào project.json; `--when` quá khứ → `BAD_INPUT`; channel lạ → `BAD_INPUT`; `list` chuẩn hóa Post có project/run; `retry` gọi đúng route; `caption` với `query_fn` giả trả text → event `caption`; CLI `social check` mã thoát 0 và event cuối `social_account`; key thiếu → event `error` `SOCIAL_AUTH`, mã thoát 1.
- [ ] **Step 2–4:** FAIL → cài đặt → PASS.
- [ ] **Step 5:** Commit `feat(engine): social check/portal/caption/publish/list/retry commands`.

### Task 3: Engine — routine

**Files:** Create `engine/autoedit/social/routine.py`, `engine/tests/test_routine.py`. Modify `commands.py`, `cli.py`, `posts.py` (`next_queue_slot`).

**Interfaces:**
- `routine.slots(now: datetime, routines: list[dict], days: int = 7) -> list[tuple[datetime, dict]]` — mọi slot routine `enabled` trong `[now, now+days)`, sắp xếp theo giờ.
- `routine.plan(now, routines, videos: list[dict], existing: list[dict]) -> list[dict]`:
  - `videos`: `[{"project": dir, "run": n, "created": iso}]` — mỗi project lấy run mới nhất, chỉ project chưa có post nào (theo `project.posts` và theo `existing` có referenceKey trỏ tới project đó), mới nhất trước.
  - `existing`: post đã có trên bundle.social trong khoảng (để bỏ slot đã có post cùng giờ ±1 phút do routine tạo — nhận diện bằng `referenceKey` bắt đầu `autoedit:`).
  - Trả `[{"slot": iso, "channels", "project", "run"}]`: gán video chưa đăng cho slot trống theo thứ tự; hết video thì dừng.
- `posts.next_queue_slot(now, routines, taken: list[str]) -> datetime`: slot routine sớm nhất không trùng `taken` (±1 phút); không có routine → ngày mai 19:30 giờ địa phương.
- Lệnh `social routine-sync --team T`: đọc `AUTOEDIT_ROUTINES`, quét `AUTOEDIT_PROJECTS_ROOT` (mỗi thư mục có `project.json`), `list_posts` 7 ngày tới, `plan`, với mỗi mục: `caption` tự động = caption AI (nếu lỗi `RateLimited`/`NoAuth` thì dùng caption dự phòng = hook + hashtag ngành từ bảng tĩnh `{thoi-trang: "#thoitrang #outfit", my-pham: "#mypham #skincare", do-an: "#monngon #review", phu-kien: "#phukien #xuhuong", chung: "#xuhuong #review"}`) → `publish(... when=slot)`. Không có routine bật → event `routine_sync` với `skipped: "Chưa bật routine"`.

- [ ] **Step 1: Test** (thời gian cố định `2026-11-20T10:00+07:00`): routine 19:30 → 7 slot bắt đầu hôm nay 19:30; routine tắt → 0 slot; 3 video chưa đăng + 7 slot → 3 mục, video mới nhất ở slot sớm nhất; project đã có `posts` bị bỏ qua; slot đã có post `autoedit:` cùng giờ bị bỏ; `next_queue_slot` không routine → `2026-11-21T19:30` giờ máy; lệnh routine-sync với FakeBundle tạo đúng số post và caption dự phòng khi `query_fn` ném `RateLimited`.
- [ ] **Step 2–4:** FAIL → cài đặt → PASS.
- [ ] **Step 5:** Commit `feat(engine): daily routines plan and create the next 7 days of posts`.

### Task 4: Engine — MCP của khách (M5)

**Files:** Create `engine/autoedit/mcp_user.py`, `engine/tests/test_mcp_user.py`. Modify `engine/autoedit/agent/options.py` (`edit_options` nhận thêm `user_mcp: dict`), `engine/autoedit/cli.py` (`_edit` truyền `mcp_user.load()`; lệnh `mcp-check`), `engine/autoedit/agent/prompt.py` (khi có MCP khách: thêm đoạn "Tool bổ sung của khách: mcp__<tên>__* — dùng khi cần thông tin sản phẩm/thương hiệu; không bắt buộc"), `agent/CLAUDE.md` (một dòng luật: tool của khách chỉ để lấy thông tin, không thay thế quy trình set_edl → finish; vẫn giới hạn 15 lượt).

**Interfaces:**
- `mcp_user.load(env=os.environ) -> dict[str, dict]`: parse `AUTOEDIT_MCP`; bỏ server tên sai luật hoặc `autoedit`; chuyển sang cấu hình SDK: stdio → `{"type":"stdio","command","args","env"}`, http → `{"type":"http","url","headers"}`; JSON hỏng → `{}` + ghi stderr (không in giá trị secret).
- `edit_options(..., user_mcp)`: `mcp_servers = {"autoedit": server, **user_mcp}`, `allowed_tools = EDIT_TOOLS + [f"mcp__{n}" for n in user_mcp]`. `strict_mcp_config=True` giữ nguyên.
- `async mcp_user.list_tools(name, cfg, timeout=20) -> list[dict]` dùng package `mcp` (`mcp.client.stdio.stdio_client` + `StdioServerParameters`, hoặc client streamable HTTP với headers) → `ClientSession.initialize()` → `list_tools()`; lỗi/timeout → `AgentFailed("Không kết nối được MCP <tên>: …")`. Đọc API thật của `mcp` 2.3.0 trong `.venv` trước khi viết.
- Lệnh `autoedit mcp-check --name X` → event `mcp_tools`.

- [ ] **Step 1: Test:** `load` lọc tên sai và `autoedit`, chuyển đúng 2 dạng; `edit_options` có server khách trong `mcp_servers` và `mcp__x` trong `allowed_tools`; `list_tools` với một MCP stdio thật viết bằng Python trong `tests/fixtures/echo_mcp.py` (dùng `mcp.server.fastmcp.FastMCP` có tool `price(sku)`) trả tool `price`; tên không có trong env → `AgentFailed`; prompt có đoạn tool bổ sung khi có MCP và không có khi không.
- [ ] **Step 2–4:** FAIL → cài đặt → PASS (kèm test cũ của options/prompt vẫn PASS).
- [ ] **Step 5:** Commit `feat(engine): customer MCP servers for the edit agent, mcp-check lists their tools`.

### Task 5: Rust — key bundle.social, routine/env, MCP config

**Files:** Create `app/src-tauri/src/mcp.rs`. Modify `secrets.rs` (`SOCIAL_ACCOUNT = "bundle-social-key"`), `settings.rs` (`social_team_id: Option<String>`, `routines: Vec<Routine>` với `#[serde(default)]` để settings.json cũ vẫn đọc được), `sidecar.rs` (`engine_env` thêm biến của Contract), `commands.rs`, `lib.rs`.

**Interfaces:**
- `mcp::load(dir) -> Vec<McpServer>` (`mcp.json`, thiếu/hỏng → rỗng), `mcp::save_server(dir, secrets, server, secret_values: HashMap)` (kiểm tên regex, ≤ 10 server, `transport` hợp lệ, stdio cần `command`, http cần `url` bắt đầu `http://` hoặc `https://`; secret rỗng → giữ cũ; khóa bị bỏ khỏi `envKeys`/`headerKeys` → xóa secret đó), `mcp::delete(dir, secrets, name)`, `mcp::engine_json(dir, secrets) -> String` (chỉ server `enabled`, secret thiếu thì bỏ khóa đó).
- `sidecar::engine_env(...)` nhận thêm `settings: &Settings` và `mcp_json: String`; thêm `BUNDLE_SOCIAL_KEY` nếu có, `AUTOEDIT_ROUTINES` (JSON routines), `AUTOEDIT_PROJECTS_ROOT`, `AUTOEDIT_MCP`.
- Commands theo bảng Contract mở rộng; `mcp_list` không bao giờ trả giá trị secret.

- [ ] **Step 1: Test:** settings.json cũ (không có `routines`) vẫn load; `engine_env` có `BUNDLE_SOCIAL_KEY` khi có key và không có khi không; `AUTOEDIT_ROUTINES` là JSON hợp lệ; `mcp::save_server` từ chối tên `autoedit`, `Bad Name`, server thứ 11, http url `ftp://`; secret lưu vào account `mcp:<tên>:<khóa>`; `engine_json` điền secret, bỏ server tắt; `mcp.json` không chứa giá trị secret (test đọc file); `delete` xóa secret.
- [ ] **Step 2–4:** FAIL → cài đặt → `cargo test` + clippy sạch.
- [ ] **Step 5:** Commit `feat(app): bundle.social key, routines and customer MCP config passed to the engine`.

### Task 6: UI — Kết nối bundle.social + onboarding bước 3

**Files:** Create `app/src/components/SocialSettings.tsx` (+ test). Modify `app/src/lib/{types,api,engine}.ts` (kiểu + hàm mới: `socialKeyStatus`, `setSocialKey`, `clearSocialKey`, `socialCheck()`, `socialPortal(team)`, `mcpList/mcpSave/mcpDelete`, `mcpCheck(name)`, `socialCaption`, `socialPublish`, `socialList`, `socialRetry`, `routineSync`), `screens/Settings.tsx` (tab "Kết nối & MCP" thay hai thẻ mờ), `screens/Onboarding.tsx` (bước 3 "Đăng bài (tùy chọn)": ô key + "Kiểm tra" + "Bỏ qua"; nút "Bắt đầu" chuyển xuống bước 3, điều kiện cũ giữ nguyên ở bước 2 để sang bước 3).

**Hành vi `SocialSettings`** (theo prototype `#t-conn` trong `ui-v6-bundle.html` / `ui-v7-subscription.html`):
- Chưa có key: ô password "Dán API key bundle.social" + "Kiểm tra" → `setSocialKey` → `socialCheck()`; lỗi `SOCIAL_AUTH` → "Key không đúng" và `clearSocialKey`.
- Có key: tên organization, chọn team (nhiều team → select; lưu `socialTeamId`; một team → tự chọn), quota "Đã đăng 11/20 bài tháng này", upload "x/y", danh sách kênh của team (icon chữ + tên + @username), nút "＋ Thêm / quản lý kênh" → `socialPortal(team)` → `openUrl(url)`; "↻ Làm mới" → `socialCheck()`; "Gỡ key" → `clearSocialKey`.
- Kênh không thuộc 4 kênh v2 hiện mờ "chưa hỗ trợ đăng video".

- [ ] **Step 1: Test:** chưa có key → nhập + Kiểm tra gọi `setSocialKey` rồi `socialCheck`, hiện quota và kênh; `SOCIAL_AUTH` → thông báo lỗi và `clearSocialKey`; nhiều team → chọn team lưu `socialTeamId`; nút portal mở URL; onboarding bước 3 "Bỏ qua" vẫn hoàn tất onboarding.
- [ ] **Step 2–4:** FAIL → cài đặt → `npm test && npm run build` PASS.
- [ ] **Step 5:** Commit `feat(app-ui): bundle.social connection settings and optional onboarding step`.

### Task 7: UI — thẻ đăng bài ở màn Kết quả

**Files:** Create `app/src/components/PostCard.tsx` (+ test). Modify `screens/Result.tsx`.

**Hành vi:**
- Chưa có key → thẻ gợi ý "Bật đăng bài tự động: Cài đặt → Kết nối" (nút mở Cài đặt tab Kết nối).
- Có key + team: chọn kênh (checkbox các kênh v2 team đang có; mặc định tất cả), caption: khi mở thẻ lần đầu gọi `socialCaption(dir, n)` điền textarea (có "↻ Viết lại"), khách sửa được; 3 lựa chọn radio "Đăng ngay" / "Chọn giờ" (input `datetime-local`, mặc định 19:30 hôm nay hoặc mai nếu đã qua) / "Vào hàng đợi"; nút "Đăng" → `socialPublish` với tiến trình upload (`step`) → hiện "Đã lên lịch 19:30 20/11 · TikTok, Instagram" hoặc lỗi qua `describeError` (thêm 3 mã `SOCIAL_*` vào `lib/errors.ts`: SOCIAL_AUTH → "Key bundle.social không dùng được", action settings; SOCIAL_LIMIT → "Hết lượt đăng của gói bundle.social", action none; SOCIAL_FAILED → "Đăng bài lỗi", action retry).
- Run đã có post (từ `project.posts`, thêm `posts` vào `ProjectDetail` — Rust `projects::detail` đọc khóa `posts`, Task 5 làm phần Rust nếu cần; nếu chưa có thì làm ở task này trong `projects.rs`) → hiện trạng thái thay cho form, có nút "Đăng thêm".
- [ ] **Step 1: Test:** không key → thẻ gợi ý; có key → caption được gọi và điền; chọn "Chọn giờ" gửi `--when` ISO có múi giờ; "Vào hàng đợi" gửi `queue`; bỏ hết kênh → nút Đăng tắt; lỗi SOCIAL_LIMIT hiện đúng câu.
- [ ] **Step 2–4:** FAIL → cài đặt → PASS.
- [ ] **Step 5:** Commit `feat(app-ui): post card on the result screen (now, pick time, queue) with AI caption`.

### Task 8: UI — tab Lịch đăng + routine

**Files:** Create `app/src/screens/Schedule.tsx`, `components/RoutineEditor.tsx` (+ tests). Modify `components/Sidebar.tsx` (tab Lịch đăng bật khi có key; không có key → mờ, bấm vào hiện "Nhập key bundle.social ở Cài đặt → Kết nối"), `state/store.tsx` (route `{name:"schedule"}`; khi khởi động nếu có key + team + routine bật → chạy `routineSync(team)` một lần, lỗi chỉ toast nhẹ).

**Hành vi `Schedule`** (theo prototype `#v-sched`, `#week` trong `ui-v6-bundle.html`):
- Mở tab → `socialList(team, đầu tuần, cuối tuần)`; nút "← Tuần trước / Tuần sau →"; chế độ "Lưới tuần" (7 cột thứ, mỗi post một ô giờ + icon kênh + màu theo trạng thái: SCHEDULED xanh dương, POSTED xanh lá, ERROR đỏ, khác xám) và "Danh sách" (theo ngày).
- Bấm post: chi tiết (caption, kênh, trạng thái, lỗi, link permalink mở bằng `openUrl`), post có project → nút "Mở project"; `ERROR` → nút "Thử lại" (`socialRetry`).
- Khối "Routine": `RoutineEditor` — danh sách routine (giờ `HH:MM`, kênh, bật/tắt, xóa), "＋ Thêm routine" (mặc định 19:30, mọi kênh v2 của team) → `saveSettings({...settings, routines})`; nút "Chạy ngay" → `routineSync(team)` → toast "Đã tạo N bài cho 7 ngày tới" hoặc `skipped`. Ghi chú nhỏ: "Routine chỉ chạy khi app mở. Bài đã lên lịch vẫn đăng khi máy tắt."
- [ ] **Step 1: Test:** tab khóa khi không có key; có key → gọi `socialList` với khoảng tuần hiện tại, hiện post ở đúng cột; Tuần sau đổi khoảng; post ERROR có "Thử lại" gọi `socialRetry`; thêm routine lưu settings; "Chạy ngay" gọi `routineSync`; store khởi động gọi `routineSync` khi đủ điều kiện và không gọi khi không.
- [ ] **Step 2–4:** FAIL → cài đặt → PASS.
- [ ] **Step 5:** Commit `feat(app-ui): schedule tab (week grid, list, retry) and daily routines`.

### Task 9: UI — quản lý MCP (M5)

**Files:** Create `app/src/components/McpSettings.tsx` (+ test). Modify `screens/Settings.tsx` (tab "Kết nối & MCP" thêm khối MCP dưới bundle.social).

**Hành vi:**
- Cảnh báo cố định: "MCP server chạy chương trình trên máy bạn. Chỉ thêm server bạn tin tưởng."
- Danh sách server: tên, loại (Lệnh / URL), công tắc bật/tắt (`mcpSave` với secrets rỗng), "Kiểm tra" → `mcpCheck(name)` → hiện danh sách tool (tên + mô tả) hoặc lỗi; "Sửa", "Xóa" (xác nhận).
- Form thêm/sửa: tên (kiểm regex Contract ngay trên form), loại: "Lệnh (stdio)" → lệnh, tham số (một ô, tách theo khoảng trắng, giữ chuỗi trong ngoặc kép), biến môi trường (các dòng KEY + giá trị password); "URL (HTTP)" → url, header (các dòng tên + giá trị password). Khi sửa, ô giá trị secret để trống nghĩa là giữ nguyên (placeholder "•••• đã lưu").
- Tối đa 10 server (nút thêm tắt khi đủ).
- [ ] **Step 1: Test:** thêm server stdio gọi `mcpSave` với `envKeys` và secrets đúng; tên `Bad Name` báo lỗi, không gọi lưu; sửa không nhập secret → secrets rỗng; Kiểm tra hiện tool từ `mcp_tools`; xóa gọi `mcpDelete` sau xác nhận; tham số có ngoặc kép tách đúng.
- [ ] **Step 2–4:** FAIL → cài đặt → PASS.
- [ ] **Step 5:** Commit `feat(app-ui): manage customer MCP servers (stdio/HTTP), check tools`.

### Task 10: Tài liệu, phiên bản, build

**Files:** Modify `docs/HUONG-DAN-CAI.md` (mục "Đăng bài tự động" + "Thêm MCP"), `docs/RELEASE.md` (không cần secret mới), spec (mục 7 ghi các quyết định: kênh v2, queue, routine qua env; thêm mục M5 ngắn mô tả MCP khách), `app/package.json` + `tauri.conf.json` + `engine/autoedit/__init__.py` + `engine/pyproject.toml` lên `0.2.0`.
- [ ] **Step 1:** Viết tài liệu, nâng phiên bản.
- [ ] **Step 2:** `scripts/build-app.sh` ra `.app`/`.dmg` 0.2.0; chạy `…/engine/autoedit social check` không có key → event `error` `SOCIAL_AUTH` (không gọi mạng thật vì thiếu key); `…/engine/autoedit mcp-check --name x` với `AUTOEDIT_MCP` trỏ tới `engine/tests/fixtures/echo_mcp.py` (qua `uv run python`) → tool `price`.
- [ ] **Step 3:** Commit `docs: v2 posting and v3 MCP guides; bump to 0.2.0`.

## Kiểm thử cuối (controller)

- Ba bộ test xanh; Opus review toàn nhánh `feat/m4-social` so với `docs/desktop-app-design`; một đợt sửa.
- Việc cần người: dán key bundle.social thật (nên dùng key mới vì key cũ đã lộ trong hội thoại trước) để kiểm `social check` và một lần đăng thử lên kênh test rồi tự xóa post trên bundle.social.
