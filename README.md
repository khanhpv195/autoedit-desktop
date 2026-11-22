# AutoEdit

App desktop (Mac, Windows) dựng video dọc TikTok/Reels/Shorts từ clip thô. Người dùng thả clip vào và trò chuyện với AI để chốt cách dựng. Engine cắt clip, chèn hook, chạy phụ đề tiếng Việt, ghép logo và nhạc rồi xuất `final.mp4`. AI chạy bằng tài khoản Claude Pro/Max của chính người dùng, qua Claude Agent SDK.

## Tính năng

- **Project:** đặt tên, đổi tên, xóa. Khi xóa project, app xóa luôn cache, transcript và file render tạm. Clip gốc của người dùng vẫn giữ nguyên.
- **Chat với AI trước khi dựng:** AI xem clip và hỏi lại những chỗ chưa rõ (thời lượng, hook, CTA, đoạn nào giữ, kiểu phụ đề), rồi đưa ra kế hoạch dựng. Việc dựng chỉ bắt đầu khi người dùng bấm "Bắt đầu edit". Mỗi project lưu lịch sử chat riêng.
- **Thời lượng:** không đặt sẵn. Prompt có nói thời lượng ("cắt còn 30s", "khoảng 1 phút") thì làm theo. Nếu không, AI tự chọn và nói rõ lý do trong kế hoạch.
- **Video mẫu:** mẫu Clip-chuan có sẵn. Ngoài ra, nút "Lưu làm mẫu" ở màn kết quả lưu một lần dựng làm mẫu để AI bắt chước ở các project sau. Quản lý các mẫu đã lưu trong Cài đặt.
- **Logo, nhạc nền, lồng tiếng:** đều tùy chọn.
- **Dựng lại theo góp ý:** mỗi lần dựng là một run riêng (`runs/N/`).
- **Đăng bài qua bundle.social:** viết caption, chọn kênh, đặt lịch, xem lịch đăng.
- **License key:** kích hoạt theo máy. Người dùng nhận bản mới qua updater.

Các rule dựng đang áp dụng: hook không che mặt người mẫu, phụ đề nằm trong vùng an toàn, có CTA. Chi tiết xem `agent/CLAUDE.md`.

## Cấu trúc repo

| Thư mục | Nội dung |
|---|---|
| `app/` | Giao diện Tauri 2. `src/` là React 19 + TypeScript, `src-tauri/` là Rust. Rust gọi engine và chuyển event lên giao diện. |
| `engine/` | Engine Python 3.12 (uv), có CLI `autoedit` in ra event dạng JSON từng dòng. Gồm prep (probe, chuẩn hóa, transcript bằng whisper), agent (Claude), render (ffmpeg), voice, social. |
| `agent/` | Prompt của agent: `CLAUDE.md` và các skill trong `.claude/skills/` (edit-video, niche-hooks, reference-edits, video-use, visual-first). Được đóng gói kèm engine. |
| `license-server/` | Cloudflare Worker + D1 cấp và kiểm tra license. Xem [license-server/README.md](license-server/README.md). |
| `license-admin/` | CLI Python để tạo và quản lý key. |
| `scripts/` | Script build: engine, tải ffmpeg/whisper, build app, ký file Mac. |
| `docs/` | [Hướng dẫn cài cho khách](docs/HUONG-DAN-CAI.md), [hướng dẫn phát hành](docs/RELEASE.md), spec và plan trong `docs/superpowers/`. |
| `spikes/` | Code thử nghiệm, không nằm trong bản phát hành. |

## Chạy dev

Máy cần có: Mac Apple Silicon, [uv](https://docs.astral.sh/uv/), Node 20+, Rust (rustup), ffmpeg (`brew install ffmpeg`), và tài khoản Claude đã đăng nhập.

```bash
# 1. Engine
cd engine
uv sync

# 2. App, chạy với engine lấy thẳng từ source
cd ../app
npm install
AUTOEDIT_ENGINE="$PWD/../engine/.venv/bin/autoedit" npm run tauri dev
```

Bản dev dùng chung dữ liệu với bản cài thật (xem mục "Dữ liệu nằm ở đâu"), nên cẩn thận khi xóa project lúc thử.

Có thể gọi engine trực tiếp để thử từng bước:

```bash
cd engine
uv run autoedit auth-check
uv run autoedit analyze --project ~/Movies/AutoEdit/<project>
uv run autoedit chat --project ~/Movies/AutoEdit/<project> --message="cắt còn 30s"
uv run autoedit edit --project ~/Movies/AutoEdit/<project> --prompt "..."
uv run autoedit reference list
```

Lệnh con: `analyze`, `chat`, `edit`, `auth-check`, `setup`, `setup-model`, `mcp-check`, `reference {save,delete,list}`, `social {check,portal,caption,publish,list,routine-sync,retry}`. Chạy `uv run autoedit <lệnh> --help` để xem tham số.

## Test

```bash
cd engine && uv run pytest -q -W error          # test "slow" (cần model whisper hoặc mạng) bị bỏ mặc định; chạy riêng: -m slow
cd app && npm test && npm run build && npm run lint
cd app/src-tauri && cargo test && cargo clippy --all-targets -- -D warnings
```

## Build bản phát hành

```bash
scripts/build-app.sh
```

Script này build engine bằng PyInstaller, tải ffmpeg và build whisper-cli (cần `cmake`), rồi build app. Kết quả nằm ở `app/src-tauri/target/release/bundle/` (`.app` và `.dmg`). Trước khi build, `app/src-tauri/license.json` phải có `url` và `pubkey`.

Muốn phát hành bản chính thức thì đẩy tag `vX.Y.Z`. Workflow `.github/workflows/release.yml` sẽ build Mac và Windows rồi tạo bản draft trên GitHub Releases. Các bước và secret cần có xem ở [docs/RELEASE.md](docs/RELEASE.md).

## Dữ liệu nằm ở đâu

| Gì | Mac | Windows |
|---|---|---|
| Project và video xuất ra | `~/Movies/AutoEdit/<ngày>_<id>/` | `Videos\AutoEdit\` |
| Dữ liệu app (cài đặt, video mẫu đã lưu, model) | `~/Library/Application Support/AutoEdit/` | `%APPDATA%\AutoEdit\` |
| Key bundle.social, secret MCP | Keychain | Credential Manager |

Thư mục một project:

- `project.json`: tên, ngành hàng, danh sách clip, các lần dựng.
- `input/`: bản chép của clip.
- `chat.json`: lịch sử chat.
- `runs/N/`: `edl.json` và `final.mp4` của lần dựng thứ N.
