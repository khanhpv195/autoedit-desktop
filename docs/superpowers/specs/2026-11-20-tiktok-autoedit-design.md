# tiktok-autoedit — Thiết kế

Ngày: 2026-11-20 · Trạng thái: chờ duyệt · Thay thế bản thiết kế web app (commit 33140a2)

## 1. Sản phẩm

**App desktop (Mac + Windows) dựng clip bán hàng ngắn** (TikTok/Reels/Shorts), bàn giao nguyên app cho **một khách** (không bán thương mại).

Người dùng chỉ làm 3 việc:
1. Chọn ngành.
2. Thả clip (thêm logo, nhạc nếu muốn).
3. Gõ một câu mô tả mơ hồ, hoặc bấm một trong 3 kịch bản AI gợi ý.

App trả về **một file `final.mp4`** đăng được ngay.

- **Mỗi project là một clip**, không dựng hàng loạt. Khách tạo project khi cần.
- **Không có preset và không có tùy chỉnh chi tiết** (kiểu phụ đề, nhịp cắt, look…). Các quyết định này nằm trong luật dựng của agent và thư viện theo ngành.
- **Không có trình sửa video.** Muốn khác đi thì gõ thêm yêu cầu rồi bấm "Dựng lại".
- **AI dùng tài khoản Claude subscription của khách** (Pro/Max), giống cách AIEV làm. Khách chấp nhận rủi ro tài khoản. API key chỉ là phương án dự phòng.
- **Không có backend riêng.** Mọi thứ chạy trên máy khách, hoặc trên dịch vụ khách tự đăng ký (Claude, bundle.social).

Bối cảnh: một người phát triển bán thời gian cùng Claude Code. Dùng lại kiến thức của skill `video-use` (MIT, browser-use) và `edit-video`.

### Phân kỳ

| Bản | Nội dung |
|---|---|
| **v1** | Dựng video: onboarding, chọn ngành, màn dựng, agent dựng, kết quả, lịch sử project |
| **v2** | Đăng bài qua bundle.social: nhập key, đăng ngay, lên lịch, mục Lịch đăng ở sidebar, routine |
| **v3** | Khách tự thêm MCP server |

Ngoài phạm vi: thanh toán, nhiều người dùng, dựng hàng loạt, cắt livestream thành clip, xuất project CapCut, trình sửa timeline, server riêng.

## 2. Kiến trúc

```
React UI ──invoke──▶ Rust (Tauri): auth · secrets · sidecar
                        │ spawn: autoedit <lệnh> --project <dir>
                        │ env: CLAUDE_CODE_OAUTH_TOKEN | ANTHROPIC_API_KEY, BUNDLE_SOCIAL_KEY
                        ▼
                 Engine Python (sidecar `autoedit`)
                   ├─ prep: ffmpeg / ffprobe / whisper-cli (sidecar)
                   ├─ agent: claude-agent-sdk ──▶ Claude (subscription của khách)
                   │     cwd = Resources/agent  (CLAUDE.md + skills)
                   │     tool: MCP chạy trong engine (get_transcript, view_frames, set_edl, render_preview, finish)
                   ├─ render + QC: ffmpeg
                   └─ social (v2): REST api.bundle.social
                        │
                 stdout JSON-lines ──▶ UI
```

| Khối | Trách nhiệm | Không làm |
|---|---|---|
| **UI** (React + TypeScript) | Các màn hình, hiện tiến trình, lịch đăng | Không xử lý video, không giữ secret |
| **Rust** (Tauri) | Hộp thoại file, Keychain/Credential Manager, dò và lấy đăng nhập Claude, spawn/kill sidecar, updater | Không chứa logic dựng |
| **Engine** (Python 3.12, PyInstaller) | Chuẩn hóa, transcript, chạy agent, render, QC, gọi bundle.social | Không biết UI |
| **Agent** (thư mục `agent/`) | Kiến thức dựng: vai trò, quy trình, luật cứng, thư viện hook theo ngành | Không chạy lệnh hệ thống |

### Giao tiếp app ↔ engine

Lệnh:
- `autoedit analyze --project <dir>`: ra 3 thẻ kịch bản.
- `autoedit edit --project <dir> --prompt "<…>"`: dựng video.
- `autoedit setup`: tải Claude Code CLI đúng phiên bản đã chốt nếu máy chưa có, in ra đường dẫn (`{"type":"setup","claude_cli":"…"}`).
- `autoedit auth-check`: kiểm tra đăng nhập Claude.
- v2: `autoedit social <lệnh> …`.

Engine in mỗi dòng stdout là một JSON:
```
{"type":"step","label":"Đang nghe lời thoại…","progress":0.2}
{"type":"agent","text":"Bỏ đoạn vấp ở 0:12","tool":"set_edl"}
{"type":"preview","path":".../work/preview.mp4","round":1}
{"type":"done","final":".../runs/1/final.mp4","summary":["…"],"usage":{"turns":9}}
{"type":"error","code":"RATE_LIMIT","message":"…","retry_at":"2026-11-20T14:30:00+07:00"}
```
Bấm Hủy thì Rust kill process. Mã lỗi: `NO_AUTH`, `RATE_LIMIT`, `BAD_INPUT`, `RENDER_FAILED`, `AGENT_FAILED`, `SETUP_REQUIRED` (chưa tải CLI Claude).

## 3. Xác thực Claude

Làm theo AIEV (`apps/server/src/config.ts` → `hasClaudeAuth`). Thứ tự dò:

1. Token app đã lưu trong Keychain/Credential Manager (`AutoEdit · claude-oauth-token`). Truyền vào engine qua `CLAUDE_CODE_OAUTH_TOKEN`.
2. Phiên đăng nhập Claude Code có sẵn trên máy: file `~/.claude/.credentials.json`, hoặc mục Keychain macOS `Claude Code-credentials`.
3. API key dự phòng (`AutoEdit · anthropic-api-key`). Truyền qua `ANTHROPIC_API_KEY`.

**Onboarding bước 1 "Đăng nhập Claude":**
- Nếu dò thấy (1) hoặc (2): hiện ✓ "Đã kết nối · subscription" và đi tiếp.
- Nếu chưa có: nút "Đăng nhập Claude" chạy `claude setup-token` bằng CLI app đã tải về. Lệnh mở trình duyệt để khách đăng nhập. Rust đọc token từ output, lưu vào Keychain, rồi chạy `autoedit auth-check` để xác nhận.
- Link phụ "Dùng API key thay thế".

**Claude Code CLI không nằm trong bộ cài.** `claude-agent-sdk` điều khiển Claude qua chương trình `claude` (Claude Code CLI, ~350MB khi giải nén). Thay vì đóng gói, engine tải nó ở lần mở đầu:
- Nguồn: wheel `claude-agent-sdk` trên PyPI đúng phiên bản SDK đã ghim, đúng nền tảng (Mac ARM/Intel, Windows x64), ~155–170MB. CLI trong wheel luôn khớp giao thức với SDK.
- Kiểm sha256 (ghim trong code), giải nén riêng file `claude`/`claude.exe` vào `<app data>/claude-cli/<phiên bản SDK>/`.
- Mọi lần gọi đều truyền `cli_path` tới file này và `DISABLE_AUTOUPDATER=1`, nên CLI không tự cập nhật. CLI Claude Code riêng của khách (nếu có) không ảnh hưởng app.
- Nâng phiên bản là việc của mình: nâng SDK + CLI cùng nhau, chạy bộ clip chuẩn, rồi phát hành qua Tauri updater. Phiên bản SDK đổi thì app tự tải CLI mới, xóa bản cũ.

Settings → AI dựng có các mục: trạng thái kết nối (subscription hay API key), nút Đăng xuất / Đổi tài khoản, và chọn model (mặc định `claude-opus-5-5`).

**Giới hạn gói subscription:** khi engine nhận lỗi rate limit, nó phát `RATE_LIMIT` kèm `retry_at`. UI báo "Đã hết lượt Claude, thử lại lúc 14:30" và giữ nguyên project để bấm dựng lại. Không hiện chi phí tiền.

## 4. Engine

### 4.1 Chuẩn bị (code, chạy một lần mỗi project, có cache)

| Bước | Công cụ | Chi tiết |
|---|---|---|
| Kiểm tra input | ffprobe | Clip ≤3 phút, đọc được. Logo PNG/JPG/SVG. Nhạc MP3/M4A/WAV. Sai thì báo `BAD_INPUT` |
| Chuẩn hóa | ffmpeg | Xoay theo metadata; HDR/HLG → SDR bt709 (zscale + tonemap); fps biến thiên → 30 CFR; 1080×1920; clip dọc → phóng (lanczos) cho kín khung, cắt phần thừa ở giữa; clip ngang → cắt giữa, nền mờ trên/dưới. Không để viền đen |
| Transcript | whisper-cli (large-v3-turbo; Metal trên Mac, Vulkan trên Windows, CPU dự phòng) | Mốc giờ từng từ; lọc câu bịa (chuỗi từ độ dài 0, câu kết kiểu "Cảm ơn các bạn đã theo dõi"); cache theo hash file |
| Khung hình | ffmpeg | ~6 keyframe cho agent xem |

### 4.2 Gợi ý kịch bản (`analyze`)

Gọi `claude-agent-sdk` `query()` một lượt, không cho dùng tool, giống `aiText.ts` của AIEV.

- Đầu vào: transcript, keyframe và file thư viện của ngành đã chọn (`agent/.claude/skills/niche-hooks/<ngành>.md`).
- Đầu ra: JSON gồm 3 thẻ `{title, hook, outline, prompt}`.
- UI hiện 3 thẻ. Bấm thẻ thì `prompt` điền vào ô mô tả. "↻ Gợi ý khác" gọi lại `analyze`, kèm danh sách thẻ đã hiện để tránh lặp.

### 4.3 Agent dựng (`edit`)

`claude-agent-sdk` `query()` với cấu hình:

```python
ClaudeAgentOptions(
    cwd=RESOURCES / "agent",                 # CLAUDE.md + .claude/skills đóng gói trong app
    setting_sources=["project"],             # không đọc ~/.claude của khách
    mcp_servers={"autoedit": create_sdk_mcp_server(tools=[...])},
    allowed_tools=["Skill", "mcp__autoedit__get_transcript", "mcp__autoedit__view_frames",
                   "mcp__autoedit__set_edl", "mcp__autoedit__render_preview", "mcp__autoedit__finish"],
    max_turns=15,
    model=settings.model,
)
```
Không có Bash, Read, Write hay Edit. Agent chỉ thao tác qua các tool sau:

| Tool | Làm gì |
|---|---|
| `get_transcript(start?, end?)` | Transcript gom cụm (ngắt khi lặng ≥0.5s), có mốc giờ |
| `view_frames(times[])` | Trả ảnh khung hình tại các mốc |
| `set_edl(edl)` | Nhận EDL (mục 4.4). Code kiểm tra: bám mốc về ranh giới từ, đệm 50ms trước / 80ms sau, bỏ đoạn <0.4s, tổng giữ lại ≥30% thời lượng có lời. Trả về EDL đã chỉnh, hoặc lỗi để agent sửa |
| `render_preview()` | Render 540p, trả vài khung hình và thời lượng; phát event `preview`. Tối đa 3 lần |
| `finish(summary[])` | Chốt EDL. Engine render bản cuối |

Prompt người dùng gửi cho agent gồm: ngành, câu mô tả, input nào có (logo, nhạc), và yêu cầu dựng lại nếu có.

Mỗi lần agent gọi tool, engine phát một event `agent` để UI hiện mục "Xem quá trình AI". Toàn bộ được ghi vào `runs/N/agent.jsonl`.

**Giới hạn và dự phòng:**
- Tối đa 15 lượt, 3 lần preview, timeout 10 phút.
- Nếu agent lỗi, hết lượt mà chưa `finish`, hoặc EDL không hợp lệ sau 2 lần sửa: dùng phương án dự phòng. Phương án này cắt lặng ≥0.6s theo luật, không có hook, và ghi rõ trong `summary`.
- Riêng `RATE_LIMIT` thì dừng hẳn và không chạy dự phòng, để khách tự chọn dựng lại sau.

### 4.4 EDL (`edl.json`)

```json
{
  "keep": [{"start": 4.12, "end": 9.80, "reason": "take 2 tốt hơn take 1"}],
  "hook": {"move_to_front": [12.4, 15.1], "text": "CHÂN NGẮN? XEM NGAY"},
  "caption_fixes": [{"at": 18.2, "wrong": "tuyết mưu", "right": "tuyết mưa"}],
  "emphasis": [{"at": 21.0, "word": "189K"}],
  "cta_text": "BẤM GIỎ HÀNG 👇",
  "music": {"use": true, "duck_db": -14}
}
```
- `hook` có thể `null`. Chữ hook tối đa 5 từ.
- Luật trong `CLAUDE.md` cấm hứa hẹn quá đà (giảm cân, cao thêm X cm, trị mụn…).

### 4.5 Render và QC (code, theo Hard Rules của video-use)

1. Mỗi đoạn được cắt riêng, kèm look theo ngành và afade 30ms ở hai đầu. Audio trung gian dùng PCM. Sau đó nối bằng `-c copy`. libx264 CRF 18.
2. Overlay theo thứ tự: chữ hook → logo (góc trên trái, tránh vùng giao diện TikTok) → CTA 2s cuối (render thành PNG để giữ emoji) → **phụ đề cuối cùng**. Phụ đề tính theo mốc giờ đầu ra, dùng font đã kiểm tra đủ dấu tiếng Việt, kiểu dựng sẵn duy nhất có nhấn từ `emphasis`.
3. Nếu có nhạc: hạ nhạc khi có lời (sidechain). Loudnorm hai lượt về -14 LUFS, true peak -1 dB.
4. QC:
   - độ dài khớp EDL ±0.1s,
   - loudness -14±1 LUFS,
   - không có khung đen >0.5s,
   - phụ đề nằm trong vùng an toàn.

   Không đạt thì render lại một lần. Vẫn không đạt thì vẫn trả file, kèm cờ `needs_review` để UI hiện cảnh báo.

### 4.6 Look theo ngành

| | Thời trang | Mỹ phẩm | Đồ ăn | Phụ kiện | Khác |
|---|---|---|---|---|---|
| Làm sáng (chỉ kênh luma) | nhẹ/vừa | nhẹ | nhẹ/vừa | nhẹ | nhẹ |
| Giữ màu sản phẩm | có | nghiêm ngặt (không đổi hue/saturation) | — | nghiêm ngặt | có |
| Saturation | giữ | giữ | +5–8% | giữ | giữ |
| Mịn da | nhẹ | **không** | không | không | không |

Agent không chỉnh look. Look do code áp dụng theo ngành.

### 4.7 Dựng lại

Engine dùng lại phần chuẩn bị đã cache, rồi chạy agent mới. Prompt gửi agent gồm câu mô tả cũ, yêu cầu mới và EDL của lần trước. Kết quả ra `runs/N+1/`. UI cho xem các lần dựng trước.

### 4.8 Trường hợp khó

| Tình huống | Xử lý |
|---|---|
| Clip không có lời | Bỏ transcript và hook. Agent chỉ chọn đoạn qua `view_frames`; render thêm look, logo, nhạc, CTA. `summary` ghi rõ |
| Clip >3 phút hoặc file hỏng | Báo `BAD_INPUT` ngay khi thả file |
| Máy Windows không có GPU | Whisper chạy CPU. UI báo thời gian ước tính trước khi chạy |
| Chưa tải model Whisper | Onboarding bắt buộc tải (~1.5GB, có thể tải tiếp nếu đứt) |
| Chưa tải CLI Claude hoặc file hỏng | Engine báo `SETUP_REQUIRED`; app đưa về bước tải. Sai sha256 thì xóa và tải lại |

## 5. Agent và skill

Thư mục `agent/` được đóng gói nguyên vẹn vào `Resources/agent/`:

```
agent/
├── CLAUDE.md                 # vai trò, quy trình (đọc transcript → xem khung → set_edl → preview ≤3 → finish), luật cứng, giới hạn
└── .claude/skills/
    ├── video-use/            # SKILL.md + LICENSE (MIT), lược bỏ phần hướng dẫn chạy lệnh ffmpeg
    ├── edit-video/           # look tự nhiên, phụ đề tiếng Việt
    └── niche-hooks/
        ├── SKILL.md
        ├── thoi-trang.md  my-pham.md  do-an.md  phu-kien.md  chung.md
```

- Mỗi file ngành có khoảng 15–20 mẫu hook/kịch bản, gồm câu mở, cấu trúc và CTA gợi ý, kèm các câu nên tránh.
- Đổi luật dựng hay thư viện hook chỉ cần sửa file `.md`, rồi phát bản cập nhật app.
- Các đoạn trong skill gốc bảo agent tự chạy ffmpeg thì được thay bằng hướng dẫn gọi tool tương ứng, vì agent không có Bash.

## 6. Giao diện

Theo prototype `docs/superpowers/prototypes/ui-v6-bundle.html` (onboarding sẽ được sửa theo mục 3).

**Sidebar**
- Tab `Video` / `Lịch đăng` (Lịch đăng có từ v2), nút "＋ Video mới".
- Danh sách project kèm trạng thái.
- Chân sidebar: tổng số video, nút Cài đặt.

**Màn hình**
1. **Onboarding**: (1) Tải Claude (~160MB, vài phút) → (2) Đăng nhập Claude, trong lúc đó model Whisper tải nền. Bản v1 chỉ có 2 bước này; bước nhập key bundle.social chuyển sang v2.
2. **Chọn ngành**: 5 thẻ (thời trang, mỹ phẩm, đồ ăn, phụ kiện, khác). Ngành dùng lần trước có nhãn "Lần trước".
3. **Màn dựng**: nút "← Đổi ngành", nhãn ngành, vùng thả clip, logo và nhạc. Khi thả clip, app tự chạy `analyze` và hiện 3 thẻ kịch bản cùng nút "↻ Gợi ý khác". Sau đó là ô mô tả và nút "Dựng video".
4. **Đang dựng**: các bước, feed hoạt động của agent, preview từng vòng, nút Hủy.
5. **Kết quả**: video, `summary`, mở thư mục, ô yêu cầu + nút "Dựng lại", mục "Xem quá trình AI" thu gọn được. Từ v2 có thêm thẻ đăng bài.
6. **Lỗi**: thông báo đọc được, kèm hành động tương ứng (dựng lại, thử lại lúc…, mở Cài đặt).
7. **Cài đặt**: tab Chung (thư mục lưu), Kết nối & MCP, AI dựng (tài khoản, model).

## 7. Đăng bài qua bundle.social (v2)

- **Khách tự quản lý kênh.** Khách tạo tài khoản bundle.social và tự nối kênh. App không làm OAuth với từng nền tảng.
- **App chỉ cần một API key**, lưu ở Keychain (`AutoEdit · bundle-social-key`).
- **Engine gọi thẳng REST `api.bundle.social`**, không chạy `bundlesocial-mcp` qua npx, để khách không phải cài Node. Các lời gọi được dùng:
  - kiểm tra key, team và quota,
  - liệt kê kênh,
  - tạo link portal để thêm/quản lý kênh,
  - upload media,
  - tạo hoặc lên lịch post,
  - liệt kê và xem post,
  - thử lại post lỗi.
- Không có lời gọi xóa hay ngắt kênh trong engine. Các thao tác đó khách làm trên bundle.social.
- **Settings → Kết nối:**
  - dán key rồi bấm Kiểm tra,
  - hiện team, quota (ví dụ 11/20), dung lượng upload, gói và danh sách kênh,
  - nút "＋ Thêm / quản lý kênh" mở trang portal,
  - nút "↻ Làm mới".
- **Chưa có key:** tab Lịch đăng bị khóa và màn Kết quả hiện gợi ý bật đăng bài. Phần dựng vẫn dùng bình thường.
- **Đăng bài:** thẻ ở màn Kết quả có 3 lựa chọn: đăng ngay, chọn giờ, hoặc vào hàng đợi. Chọn kênh, caption do AI viết (`query()` một lượt) và khách sửa được.
- **Lịch đăng:**
  - lưới tuần và danh sách, đồng bộ từ danh sách post khi mở app hoặc mở tab (không dùng webhook),
  - post đã lên lịch chạy trên server bundle.social nên vẫn đăng khi máy tắt.
- **Routine** (ví dụ "mỗi ngày 19:30 đăng video mới nhất chưa đăng"): chỉ chạy khi app mở. Mỗi lần mở app, routine tạo sẵn post cho 7 ngày tới trên bundle.social.

## 8. Cấu trúc repo và bản bàn giao

**Repo**
```
tiktok-autoedit/
├── app/                      # Tauri
│   ├── src/                  # React: screens/, components/, lib/engine.ts
│   └── src-tauri/            # Rust: auth.rs, secrets.rs, sidecar.rs; binaries/; tauri.conf.json
├── engine/                   # Python
│   ├── autoedit/             # cli, events, prep/, agent/ (runner, tools, analyze), edl, render/, social/, fallback
│   ├── tests/ + fixtures/
│   └── autoedit.spec         # PyInstaller
├── agent/                    # CLAUDE.md + .claude/skills
├── scripts/                  # build sidecar, tải ffmpeg/whisper
├── .github/workflows/release.yml
└── docs/
```

**Bộ cài:** `AutoEdit.dmg` cho Mac (ARM, ký và notarize), `AutoEdit-setup.exe` cho Windows (có ký). Khoảng 200MB (ước tính: engine 55MB đo thật trên Mac ARM + ffmpeg/ffprobe bản tĩnh ~120MB ước tính + whisper-cli ~10MB ước tính + app Tauri ~15MB ước tính; bản ffmpeg Homebrew động không dùng được để đo vì cần thư viện đi kèm, cả thư mục cài khoảng 51MB), gồm:
- app Tauri,
- sidecar `autoedit` (không kèm Claude Code CLI), ffmpeg, ffprobe, whisper-cli,
- `Resources/agent/`,
- `assets/` (font, PNG cho CTA).

Khách không phải tự cài gì. Lần mở đầu app tự tải CLI Claude (~160MB) và model Whisper (~1.5GB). Tự cập nhật qua Tauri updater, lấy bản mới từ GitHub Releases của repo phát hành (endpoint `https://github.com/<repo>/releases/latest/download/latest.json`, workflow phát hành điền tên repo lúc build).

**Dữ liệu trên máy khách**
```
~/Movies/AutoEdit/<ngày>_<tên>/          # Windows: Videos\AutoEdit\
├── input/  clip, logo, nhạc
├── project.json                         # ngành, prompt, kịch bản đã chọn, trạng thái, các lần dựng
├── work/   normalized.mp4, transcript.json, frames/, edl.json, preview.mp4
└── runs/N/ final.mp4, run.log, agent.jsonl
~/Library/Application Support/AutoEdit/  # Windows: %APPDATA%\AutoEdit\
├── models/ggml-large-v3-turbo.bin
├── claude-cli/0.2.186/claude          # Windows: claude.exe; tải từ wheel PyPI
├── settings.json
└── logs/
```

## 9. Kiểm thử

- **Bộ clip chuẩn:** khoảng 10 clip thật, 2 clip mỗi ngành, có các trường hợp ồn, HDR iPhone, quay ngang, nói vấp, không lời. Có script chạy cả bộ, xuất bảng ảnh tổng hợp và bảng QC để xem bằng mắt mỗi lần sửa engine hoặc `agent/`.
- **Unit test (pytest):**
  - kiểm tra EDL trong `set_edl`: bám ranh giới từ, đệm, đoạn ngắn, tỉ lệ giữ lại,
  - mốc giờ SRT sau khi nối,
  - lọc câu bịa,
  - chuẩn hóa: xoay, HDR, clip ngang,
  - QC.
- **Agent:**
  - thay `query()` bằng chuỗi message giả lập để test giới hạn lượt, số lần preview, timeout, lỗi `RATE_LIMIT`, và việc chuyển sang phương án dự phòng,
  - chạy thật với bộ clip chuẩn khi sửa `CLAUDE.md` hoặc skill (tốn lượt subscription, làm có chủ đích).
- **Event:** kiểm tra mỗi loại event JSON-lines đúng schema.
- **App:** Playwright trên UI với sidecar giả lập; smoke test bản build thật trên Mac ARM và Windows 11.
- **bundle.social (v2):** dùng tài khoản test, upload rồi lên lịch, kiểm tra trạng thái, sau đó hủy post.

## 10. Mốc

| Mốc | Nội dung | Kết quả dùng được |
|---|---|---|
| M1 | Engine CLI: chuẩn bị, `analyze`, agent + tool, render, QC, dự phòng; `agent/` với 5 thư viện ngành; bộ clip chuẩn | Chạy `autoedit edit` từ terminal ra `final.mp4` đạt chất lượng |
| M2 | App Tauri: onboarding (tải CLI Claude, đăng nhập Claude, tải model), chọn ngành, màn dựng, đang dựng, kết quả, lỗi, cài đặt; đóng gói sidecar Mac + Windows | Khách dùng thử trên máy dev |
| M3 | Ký app, notarize, updater, hướng dẫn cài | **Bàn giao v1** |
| M4 | bundle.social: key, đăng ngay, lên lịch, tab Lịch đăng, routine | **Bàn giao v2** |
| M5 | Khách tự thêm MCP server | v3 |

Ngay đầu M1 phải xác nhận: `claude-agent-sdk` Python chạy được bên trong PyInstaller với CLI đặt ngoài package qua `cli_path`, `setup-token` hoạt động, và skill được nạp qua `setting_sources=["project"]`.

## 11. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Anthropic không cho app bên thứ ba dùng đăng nhập subscription; tài khoản khách có thể bị hạn chế | Khách đã chấp nhận rủi ro; giữ phương án dự phòng API key, đổi qua Cài đặt |
| Hết lượt subscription giữa chừng | Lỗi `RATE_LIMIT` kèm giờ thử lại; project giữ nguyên |
| Claude Code CLI hoặc SDK đổi cách đăng nhập | Ghim phiên bản SDK; cập nhật qua updater |
| CLI ghim lâu bị Anthropic ngừng hỗ trợ | Nâng SDK + CLI định kỳ, chạy bộ clip chuẩn, phát hành qua updater; engine báo rõ "cần cập nhật app" |
| PyPI đổi URL hoặc gỡ file wheel | URL + sha256 ghim trong code; nếu hỏng thì phát hành bản app với URL mới (có thể tự host bản sao trên GitHub Releases) |
| Whisper sai tiếng Việt (tên sản phẩm, tiếng lóng) | `caption_fixes` từ agent; câu mô tả của khách làm ngữ cảnh |
| Whisper chậm trên máy Windows không có GPU | Dùng CPU, báo thời gian ước tính |
| Chất lượng agent dao động giữa các lần chạy | Luật cứng kiểm tra bằng code, render bằng code, có preview để agent tự sửa, có phương án dự phòng |
| Cảnh báo "app không rõ nguồn gốc" | Apple Developer ($99/năm) và chứng chỉ ký code Windows |
| Gói Free bundle.social chỉ 20 post/tháng; API có thể đổi | Hiện quota trong app; chỉ dùng tập lời gọi nhỏ, dễ sửa |
