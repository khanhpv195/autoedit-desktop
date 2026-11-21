# Hướng dẫn phát hành (cho người phát triển)

## 1. Một lần: tạo repo và secret

1. Tạo repo GitHub, push code lên nhánh chính.
2. Vào Settings → Secrets and variables → Actions, thêm các secret sau.

| Secret | Lấy ở đâu |
|---|---|
| `APPLE_CERTIFICATE` | Chứng chỉ "Developer ID Application" xuất ra `.p12`, rồi `base64 -i cert.p12 \| pbcopy` |
| `APPLE_CERTIFICATE_PASSWORD` | Mật khẩu đặt lúc xuất `.p12` |
| `APPLE_SIGNING_IDENTITY` | Chuỗi `Developer ID Application: Tên (TEAMID)`, xem bằng `security find-identity -v -p codesigning` |
| `APPLE_ID` | Email Apple Developer |
| `APPLE_PASSWORD` | App-specific password, tạo tại appleid.apple.com → Đăng nhập và bảo mật |
| `APPLE_TEAM_ID` | developer.apple.com → Membership details |
| `TAURI_SIGNING_PRIVATE_KEY` | Nội dung file `~/.tauri/autoedit-updater.key` |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | Để rỗng (khóa sinh với mật khẩu rỗng) |
| `WINDOWS_CERTIFICATE` | File `.pfx` mã hóa base64: `certutil -encode cert.pfx cert.b64` hoặc `base64 -i cert.pfx` |
| `WINDOWS_CERTIFICATE_PASSWORD` | Mật khẩu của `.pfx` |

Thiếu secret Apple hoặc Windows thì workflow vẫn build, chỉ không ký và có cảnh báo.

Khóa updater riêng nằm ở `~/.tauri/autoedit-updater.key`, không nằm trong repo. Sao lưu nó. Mất khóa thì khách đang dùng không nhận được bản cập nhật nữa. Khóa công khai đã nằm trong `app/src-tauri/tauri.conf.json`.

## 2. Mỗi lần phát hành

1. Nâng phiên bản ở `app/src-tauri/tauri.conf.json` và `app/package.json`.
2. Chạy đủ test: engine, giao diện, Rust (xem mục 4).
3. Commit, rồi `git tag vX.Y.Z && git push --tags`.
4. Workflow `release` build Mac (arm64) và Windows, tạo bản draft trên GitHub Releases.
5. Mở bản draft, thử cài, rồi bấm Publish. Updater của khách đọc `latest.json` từ bản mới nhất đã publish.

Bản v0.2.0 (đăng bài, MCP) không cần thêm secret CI nào. Key bundle.social và secret MCP do khách nhập trong app và nằm trong Keychain trên máy khách.

## 3. Nâng Claude SDK và CLI

1. Sửa `SDK_VERSION` và `WHEELS` trong `engine/autoedit/claude_cli.py`.
2. Chạy bộ clip chuẩn (`engine/bench`).
3. Chạy một lần dựng thật bằng bản build.
4. Phát hành như mục 2.

## 4. Build thử trên máy

```
scripts/build-app.sh
```

Script build engine, lấy ffmpeg và whisper-cli (cần `cmake`), rồi build app. Kết quả ở `app/src-tauri/target/release/bundle/`:

- `macos/AutoEdit.app`
- `dmg/AutoEdit_0.2.0_aarch64.dmg`

Bản local ký ad-hoc. Để thử ký thật, chạy `scripts/sign-mac-resources.sh "<identity>"` trước `npm run tauri build`.

Test:

```
cd engine && uv run pytest -q -W error
cd app && npm test && npm run build
cd app/src-tauri && cargo test && cargo clippy --all-targets -- -D warnings
```

## 5. Ghi chú về ffmpeg

Bản ffmpeg dựng sẵn lấy từ ffmpeg.martin-riedl.de (build GPL, có libx264, libass, zimg). Script ghim URL và sha256. Khi phát hành thương mại, xem lại giấy phép GPL của bản này. Muốn đổi nguồn, sửa `scripts/fetch-bins-mac.sh`; script tự kiểm các filter engine cần.

## 6. License

- Bản phát hành cần `app/src-tauri/license.json` đã điền `url` và `pubkey` (xem `license-server/README.md`). Để trống thì build release dừng ngay trong `build.rs`, và `scripts/build-app.sh` dừng trước khi build.
- Build debug vẫn chạy với `license.json` trống. Đặt `AUTOEDIT_LICENSE_DEV=1` khi chạy bản debug để bỏ qua màn kích hoạt.
- Khóa ký riêng (private key) và admin token chỉ nằm trong trình quản lý mật khẩu và trong secret của Worker. Không commit.
- Đổi khóa ký nghĩa là phải phát hành bản mới, và mọi khách phải kích hoạt lại.
