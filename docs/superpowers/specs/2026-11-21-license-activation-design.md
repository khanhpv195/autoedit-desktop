# License activation — design

Approved direction 2026-11-21. The customer only pastes a key and presses **Kích hoạt**. Each key activates on one machine. We create, list, revoke and reset keys from our own machine with a CLI.

## Goals and non-goals
- Goal: stop casual sharing of the installer. A key used on machine A is refused on machine B.
- Goal: the customer never sees or handles a machine code.
- Goal: no server to start, stop or maintain on our side, and no recurring cost.
- Non-goal: resisting a skilled cracker who patches the binary. This is a gate against casual sharing, not DRM.

## Components

### 1. Activation API: `license-server/` (Cloudflare Worker + D1, free tier)
- One D1 table `keys`:
  - `key` TEXT PK. The plain key, so we can resend it to a customer.
  - `name` TEXT and `note` TEXT.
  - `created_at`.
  - `machine` TEXT NULL. The machine hash, set on first activation.
  - `activated_at` and `last_seen_at`.
  - `app_version`.
  - `status` TEXT: `active` or `revoked`.
- Public endpoints, JSON:
  - `POST /v1/activate {key, machine, app_version}`:
    - `200 {license}` when the key is unbound, which binds it, or already bound to this same machine (idempotent).
    - `404 invalid`: unknown key.
    - `409 used_elsewhere`: bound to another machine.
    - `410 revoked`.
  - `POST /v1/check {key, machine}`:
    - `200 {status: "active"}` and updates `last_seen_at`.
    - `410 revoked`.
    - `409 used_elsewhere`: after a reset, the key was activated on another machine.
    - `404 invalid`.
- Admin endpoints use `Authorization: Bearer <ADMIN_TOKEN>`, a Worker secret, compared in constant time:
  - `POST /v1/admin/keys {name, note}` → `{key}`
  - `GET /v1/admin/keys`
  - `POST /v1/admin/keys/:key/revoke`
  - `POST /v1/admin/keys/:key/reset`: clears `machine` and sets status back to `active`.
- Key format: `AE-XXXX-XXXX-XXXX-XXXX`. Crockford base32 from `crypto.getRandomValues`, 80 bits, so it cannot be guessed.
- License token: `base64url(JSON{key, machine, name, iat}) + "." + base64url(Ed25519 signature)`.
  - The private key is the Worker secret `LICENSE_SIGNING_KEY`.
  - The public key is compiled into the app.

### 2. Admin CLI: `license-admin/` (Python, uv, stdlib only)
- `license-admin setup`:
  - Asks for the Worker URL and the admin token.
  - Stores them in `~/.autoedit-license/config.json` with mode 0600, outside the repo.
- `license-admin keygen`:
  - Generates the Ed25519 pair.
  - Prints the private key once, to paste into `wrangler secret put LICENSE_SIGNING_KEY`.
  - Writes the public key for the app build.
- Key commands:
  - `license-admin create "Tên khách" [--note ...]` prints the key.
  - `license-admin list` shows a table: key, customer, status, machine (short), activation date, last seen.
  - `license-admin revoke <key>`.
  - `license-admin reset <key>`, used when the customer changes machine.
- `license-server/README.md` has the one-time deploy steps: `wrangler login`, `d1 create`, apply the migration, `secret put` for the admin token and signing key, `deploy`.

### 3. App gate: Tauri, Rust + React
- **Machine hash:**
  - SHA-256 of `"autoedit:" + id`, as 32 hex characters.
  - `id` is the IOPlatformUUID (`ioreg -rd1 -c IOPlatformExpertDevice`) on macOS and the registry value `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid` on Windows.
  - The customer never sees it.
- **Storage:** the license token is kept in Keychain, service `AutoEdit`, account `license`.
- **At startup:**
  - Rust verifies the token offline: Ed25519 signature with the embedded public key, then a `machine` match.
  - Valid → licensed. Otherwise → unlicensed.
- **Enforced in Rust:**
  - Every Tauri command returns the error `LICENSE_REQUIRED` while unlicensed, except: `license_status`, `license_activate`, app version and updater commands.
  - This is enforced by a guard at the top of each command, not just hidden in the UI.
- **Revocation check:**
  - Calls `/v1/check` at startup (in the background, never blocking the UI) and then every 6 hours.
  - `410` or `409`: delete the token, switch to unlicensed and emit an event. The UI shows the activation screen with the reason.
  - Network errors and 5xx: ignored, the app keeps working offline. There is no offline time limit.
- **Activation screen**, shown before onboarding when unlicensed: a key input, a **Kích hoạt** button and Vietnamese errors:

  | Case | Message |
  |---|---|
  | 404 | "Key không đúng" |
  | 409 | "Key đã được kích hoạt trên máy khác. Liên hệ người bán để được hỗ trợ." |
  | 410 | "Key đã bị thu hồi" |
  | Offline | "Không kết nối được máy chủ kích hoạt, kiểm tra mạng rồi thử lại" |

- **Build config:** the API URL and the public key are compile-time constants, `AUTOEDIT_LICENSE_URL` and `AUTOEDIT_LICENSE_PUBKEY`.
  - A release build without them fails to compile.
  - Debug builds may skip the gate only when `AUTOEDIT_LICENSE_DEV=1` is set, under `cfg(debug_assertions)`.

## Data flow
1. We run `license-admin create "Shop A"` and send the key to the customer.
2. The customer opens the app, pastes the key and presses Kích hoạt. The app POSTs `/v1/activate` with the key and machine hash.
3. The API binds the machine and returns the signed token. The app stores it in Keychain and unlocks.
4. On later launches the app works offline from the token. When online, it calls `/check` every 6 hours.
5. Someone shares the installer and key: activation on machine B gets 409 and is refused.
6. We run `license-admin revoke` and the customer's app locks at its next check.
7. The customer changes machine: we run `license-admin reset` and the customer activates on the new machine.

## Testing
- **Worker:** vitest against the Worker with a local D1, through Miniflare or the `wrangler` test pool.
  - Activate: unbound, same machine, other machine, revoked, unknown.
  - Check.
  - Admin auth required.
  - Reset.
  - Token signature verifies with the public key.
- **Admin CLI:** pytest with a fake HTTP server: create, list, revoke, reset and config file permissions.
- **Rust:**
  - Token verification: good, bad signature, other machine, malformed.
  - Guard blocks commands while unlicensed.
  - Check response handling: revoked → token deleted.
  - Machine hash is stable.
- **UI:** vitest for the activation screen states and error messages.

## Rollout
- Built on its own branch after the multi-clip work is reviewed and merged.
- Needs from the user, once:
  - a free Cloudflare account and running the deploy steps;
  - keeping the admin token and signing private key safe, in a password manager.
