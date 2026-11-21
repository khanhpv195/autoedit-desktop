# AutoEdit License Server

Cloudflare Worker + D1. Mỗi key gắn với máy đầu tiên kích hoạt nó và trả về token ký Ed25519. App kiểm tra token offline bằng public key.

## Cài đặt một lần

1. `cd license-server && npm install`
2. `npx wrangler login`
3. `npx wrangler d1 create autoedit-license`, rồi dán `database_id` được in ra vào `wrangler.toml`.
4. `npm run migrate`
5. `npm run keygen`. Lưu cả hai giá trị vào password manager.
6. `npx wrangler secret put LICENSE_SIGNING_KEY` (dán giá trị PRIVATE).
7. `openssl rand -hex 32`, rồi `npx wrangler secret put ADMIN_TOKEN` (dán chuỗi vừa tạo).
8. `npm run deploy`, ghi lại URL `https://autoedit-license.<subdomain>.workers.dev`.
9. Điền `url` và `pubkey` vào `app/src-tauri/license.json` rồi commit (cả hai đều công khai).
10. `cd ../license-admin && uv run license-admin setup` (nhập URL + admin token).

## Dùng hằng ngày

- `uv run license-admin create "Tên khách"`: tạo key mới
- `uv run license-admin list`: xem danh sách key
- `uv run license-admin revoke <key>`: thu hồi key
- `uv run license-admin reset <key>`: gỡ ràng buộc máy (khách đổi máy) và kích hoạt lại key đã thu hồi

## Sự cố

- **Mất signing key**: phải build lại app với public key mới và mọi khách phải kích hoạt lại.
- **Mất admin token**: đặt token mới bằng `npx wrangler secret put ADMIN_TOKEN`, rồi chạy lại `license-admin setup`.
- Không bao giờ commit admin token hoặc signing key (PRIVATE).

## Phát triển

`npm test` chạy vitest với DB trong bộ nhớ; `npx tsc` kiểm tra kiểu; `npx wrangler deploy --dry-run --outdir /tmp/x` kiểm tra bundle mà không cần đăng nhập.
