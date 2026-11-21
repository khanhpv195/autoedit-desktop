# License Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the customer pastes a key, presses **Kích hoạt**, and the app unlocks on that one machine. We create, list, revoke and reset keys from our machine with a CLI.

**Architecture:**
- **Activation API.** A tiny Cloudflare Worker + D1 binds each key to the first machine that activates it. It returns an Ed25519-signed license token.
- **App gate.** The Tauri app verifies the token offline, using a public key compiled in. A central gate in the Rust invoke handler blocks every command until the app is licensed. A background check every 6 h locks the app again if the key was revoked.
- **Admin CLI.** A stdlib-only Python CLI calls the Worker's admin endpoints with a bearer token.

**Tech Stack:**
- Worker: TypeScript, Cloudflare Workers, D1, WebCrypto Ed25519, vitest on Node 24.
- Admin CLI: Python 3.12 stdlib, uv, pytest.
- App gate: Rust with `ed25519-dalek` 2, `sha2`, `base64`, `reqwest` 0.13 (already in the lock tree via the updater).
- UI: React/TS, vitest.

**Spec:** `docs/superpowers/specs/2026-11-21-license-activation-design.md`

## Global Constraints

**Key and token formats**
- Key format: `AE-XXXX-XXXX-XXXX-XXXX`, Crockford base32 (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`), 80 random bits.
- Token: `base64url(JSON{key, machine, name, iat})` + `.` + `base64url(Ed25519 signature over the first part's ASCII bytes)`, no padding.
- Machine hash: the first 32 hex characters of `SHA-256("autoedit:" + platform id)`, lowercase.
  - Platform id on macOS: IOPlatformUUID.
  - Platform id on Windows: MachineGuid.

**API endpoints**
- Public endpoints:
  - `POST /v1/activate` → 200 `{license}`, or 404 `{error:"invalid"}`, 409 `{error:"used_elsewhere"}`, 410 `{error:"revoked"}`.
  - `POST /v1/check` → 200 `{status:"active"}`, or 404, 409, 410 with the same bodies.
  - Malformed JSON gets 400 `{error:"bad_request"}`.
- Admin endpoints need `Authorization: Bearer <ADMIN_TOKEN>`, else 401. The comparison is constant-time.
  - `POST /v1/admin/keys {name, note?}` → `{key}`
  - `GET /v1/admin/keys` → `{keys:[...]}`
  - `POST /v1/admin/keys/:key/revoke` → `{ok:true}`
  - `POST /v1/admin/keys/:key/reset` → `{ok:true}`
  - Unknown key → 404.

**App behaviour**
- App error codes from license commands: `LICENSE_INVALID`, `LICENSE_USED`, `LICENSE_REVOKED`, `LICENSE_OFFLINE`, `LICENSE_REQUIRED`.
- Vietnamese UI copy:
  - `LICENSE_INVALID`: "Key không đúng"
  - `LICENSE_USED`: "Key đã được kích hoạt trên máy khác. Liên hệ người bán để được hỗ trợ."
  - `LICENSE_REVOKED`: "Key đã bị thu hồi"
  - `LICENSE_OFFLINE`: "Không kết nối được máy chủ kích hoạt, kiểm tra mạng rồi thử lại"
- Keychain: service `AutoEdit`, account `license`. Use the existing `SecretStore` trait in `app/src-tauri/src/secrets.rs`.
- Background check: at startup, then every 6 h. Network errors and 5xx are ignored, and there is no offline time limit.

**Secrets and builds**
- Never commit the admin token or the signing private key.
- The Ed25519 public key and the Worker URL are public and live in `app/src-tauri/license.json`.
- A release build with an empty `license.json` must fail. A debug build skips the gate only when `AUTOEDIT_LICENSE_DEV=1` is set.
- Every HTTP client sends its own User-Agent; Cloudflare 403s `Python-urllib`. The admin CLI uses `AutoEdit-License-Admin/1`.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` for subagents.

---

## File Structure

```
license-server/                     Cloudflare Worker (new)
  package.json, tsconfig.json, wrangler.toml, vitest.config.ts
  migrations/0001_init.sql          keys table
  src/core.ts                       pure: key gen, token signing, request handling over a Db interface
  src/db.ts                         Db interface + D1 implementation
  src/index.ts                      Worker entry: wires env -> core.handle
  scripts/keygen.mjs                prints a new Ed25519 pair (PKCS8 private b64, raw public b64)
  test/core.test.ts                 vitest with an in-memory Db
  README.md                         one-time deploy + daily use
license-admin/                      Python CLI (new)
  pyproject.toml
  license_admin/__init__.py, cli.py
  tests/test_cli.py
app/src-tauri/
  license.json                      {"url": "", "pubkey": ""} committed; filled after deploy
  build.rs                          reads license.json -> rustc env; release + empty => panic
  src/license.rs                    machine hash, token verify, Gate state, activate/check HTTP, allowed()
  src/lib.rs                        manage Gate, central invoke gate, background check loop
  src/commands.rs                   license_status, license_activate commands
app/src/
  lib/api.ts, lib/types.ts          licenseStatus, licenseActivate
  screens/Activate.tsx (+ test)     activation screen
  state/store.tsx, App.tsx          route "activate", boot order, revoked event
scripts/build-app.sh                fail early with a clear message if license.json is empty
```

---

### Task 1: Worker core (keys, tokens, handler) with in-memory tests

**Files:**
- Create:
  - `license-server/package.json`, `license-server/tsconfig.json`, `license-server/vitest.config.ts`
  - `license-server/src/db.ts`, `license-server/src/core.ts`
  - `license-server/scripts/keygen.mjs`
  - `license-server/test/core.test.ts`
- Modify: `.gitignore` (add `license-server/node_modules/`, `license-server/.wrangler/`)

**Interfaces:**
- Produces:
  - `handle(req: Request, env: CoreEnv, db: Db, now?: () => Date): Promise<Response>`
  - `type CoreEnv = { ADMIN_TOKEN: string; LICENSE_SIGNING_KEY: string }`, where `LICENSE_SIGNING_KEY` is the PKCS8 private key, base64.
  - `interface Db`:
    - `get(key): Promise<KeyRow|null>`
    - `insert(row): Promise<void>`
    - `update(key, patch: Partial<KeyRow>): Promise<void>`
    - `list(): Promise<KeyRow[]>`
  - `newKey(): string`

- [ ] **Step 1: Scaffold**

`license-server/package.json`:
```json
{
  "name": "autoedit-license-server",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "vitest run",
    "keygen": "node scripts/keygen.mjs",
    "deploy": "wrangler deploy",
    "migrate": "wrangler d1 migrations apply autoedit-license --remote"
  },
  "devDependencies": {
    "@cloudflare/workers-types": "^4",
    "typescript": "^5",
    "vitest": "^3",
    "wrangler": "^4"
  }
}
```
`license-server/tsconfig.json`:
```json
{ "compilerOptions": { "target": "es2022", "module": "es2022", "moduleResolution": "bundler", "strict": true,
  "lib": ["es2022"], "types": ["@cloudflare/workers-types"], "noEmit": true }, "include": ["src", "test"] }
```
`license-server/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";
export default defineConfig({ test: { environment: "node" } });
```
Run: `cd license-server && npm install`

- [ ] **Step 2: Write `src/db.ts`**

```ts
export type KeyRow = {
  key: string; name: string; note: string; created_at: string;
  machine: string | null; activated_at: string | null; last_seen_at: string | null;
  app_version: string | null; status: "active" | "revoked";
};

export interface Db {
  get(key: string): Promise<KeyRow | null>;
  insert(row: KeyRow): Promise<void>;
  update(key: string, patch: Partial<KeyRow>): Promise<void>;
  list(): Promise<KeyRow[]>;
}

const COLS = ["name", "note", "machine", "activated_at", "last_seen_at", "app_version", "status"] as const;

export class D1Db implements Db {
  constructor(private d1: D1Database) {}
  async get(key: string) {
    return (await this.d1.prepare("SELECT * FROM keys WHERE key = ?").bind(key).first<KeyRow>()) ?? null;
  }
  async insert(r: KeyRow) {
    await this.d1.prepare("INSERT INTO keys (key,name,note,created_at,machine,activated_at,last_seen_at,app_version,status) VALUES (?,?,?,?,?,?,?,?,?)")
      .bind(r.key, r.name, r.note, r.created_at, r.machine, r.activated_at, r.last_seen_at, r.app_version, r.status).run();
  }
  async update(key: string, patch: Partial<KeyRow>) {
    const cols = COLS.filter((c) => c in patch);
    if (!cols.length) return;
    await this.d1.prepare(`UPDATE keys SET ${cols.map((c) => `${c} = ?`).join(", ")} WHERE key = ?`)
      .bind(...cols.map((c) => patch[c] ?? null), key).run();
  }
  async list() {
    return (await this.d1.prepare("SELECT * FROM keys ORDER BY created_at DESC").all<KeyRow>()).results;
  }
}

export class MemoryDb implements Db {
  rows = new Map<string, KeyRow>();
  async get(key: string) { const r = this.rows.get(key); return r ? { ...r } : null; }
  async insert(r: KeyRow) { this.rows.set(r.key, { ...r }); }
  async update(key: string, patch: Partial<KeyRow>) { const r = this.rows.get(key); if (r) Object.assign(r, patch); }
  async list() { return [...this.rows.values()].sort((a, b) => b.created_at.localeCompare(a.created_at)); }
}
```

- [ ] **Step 3: Write the failing tests `test/core.test.ts`**

```ts
import { describe, expect, it, beforeAll } from "vitest";
import { handle, newKey, type CoreEnv } from "../src/core";
import { MemoryDb } from "../src/db";

let env: CoreEnv;
let pub: CryptoKey;

beforeAll(async () => {
  const kp = (await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"])) as CryptoKeyPair;
  const pkcs8 = new Uint8Array(await crypto.subtle.exportKey("pkcs8", kp.privateKey));
  env = { ADMIN_TOKEN: "admin-secret", LICENSE_SIGNING_KEY: Buffer.from(pkcs8).toString("base64") };
  pub = kp.publicKey;
});

const post = (path: string, body: unknown, auth?: string) =>
  new Request("https://x" + path, { method: "POST", body: JSON.stringify(body),
    headers: { "content-type": "application/json", ...(auth ? { authorization: `Bearer ${auth}` } : {}) } });
const get = (path: string, auth?: string) =>
  new Request("https://x" + path, { headers: auth ? { authorization: `Bearer ${auth}` } : {} });

async function create(db: MemoryDb, name = "Shop A") {
  const r = await handle(post("/v1/admin/keys", { name }, "admin-secret"), env, db);
  expect(r.status).toBe(200);
  return ((await r.json()) as { key: string }).key;
}

function b64urlToBytes(s: string) { return Uint8Array.from(Buffer.from(s, "base64url")); }

describe("keys", () => {
  it("newKey has the AE-XXXX-XXXX-XXXX-XXXX shape and is random", () => {
    const k = newKey();
    expect(k).toMatch(/^AE-[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{4}){3}$/);
    expect(newKey()).not.toBe(k);
  });
});

describe("admin", () => {
  it("rejects missing or wrong token", async () => {
    const db = new MemoryDb();
    expect((await handle(post("/v1/admin/keys", { name: "x" }), env, db)).status).toBe(401);
    expect((await handle(post("/v1/admin/keys", { name: "x" }, "nope"), env, db)).status).toBe(401);
    expect((await handle(get("/v1/admin/keys", "nope"), env, db)).status).toBe(401);
  });
  it("creates and lists keys", async () => {
    const db = new MemoryDb();
    const k = await create(db, "Shop A");
    const r = await handle(get("/v1/admin/keys", "admin-secret"), env, db);
    const body = (await r.json()) as { keys: { key: string; name: string; status: string }[] };
    expect(body.keys.map((x) => [x.key, x.name, x.status])).toEqual([[k, "Shop A", "active"]]);
  });
  it("create needs a name", async () => {
    expect((await handle(post("/v1/admin/keys", { name: " " }, "admin-secret"), env, new MemoryDb())).status).toBe(400);
  });
  it("revoke and reset unknown key give 404", async () => {
    const db = new MemoryDb();
    expect((await handle(post("/v1/admin/keys/AE-NOPE/revoke", {}, "admin-secret"), env, db)).status).toBe(404);
    expect((await handle(post("/v1/admin/keys/AE-NOPE/reset", {}, "admin-secret"), env, db)).status).toBe(404);
  });
});

describe("activate", () => {
  it("binds the first machine and returns a token signed for it", async () => {
    const db = new MemoryDb();
    const k = await create(db);
    const r = await handle(post("/v1/activate", { key: k, machine: "m1", app_version: "0.3.0" }), env, db);
    expect(r.status).toBe(200);
    const { license } = (await r.json()) as { license: string };
    const [payload, sig] = license.split(".");
    expect(await crypto.subtle.verify({ name: "Ed25519" }, pub, b64urlToBytes(sig), new TextEncoder().encode(payload))).toBe(true);
    const p = JSON.parse(Buffer.from(payload, "base64url").toString());
    expect(p).toMatchObject({ key: k, machine: "m1", name: "Shop A" });
    expect(typeof p.iat).toBe("number");
    expect((await db.get(k))!.machine).toBe("m1");
  });
  it("same machine again is fine, another machine is 409", async () => {
    const db = new MemoryDb();
    const k = await create(db);
    await handle(post("/v1/activate", { key: k, machine: "m1" }), env, db);
    expect((await handle(post("/v1/activate", { key: k, machine: "m1" }), env, db)).status).toBe(200);
    const r = await handle(post("/v1/activate", { key: k, machine: "m2" }), env, db);
    expect(r.status).toBe(409);
    expect(await r.json()).toEqual({ error: "used_elsewhere" });
  });
  it("unknown key 404, revoked 410, bad body 400", async () => {
    const db = new MemoryDb();
    const k = await create(db);
    expect((await handle(post("/v1/activate", { key: "AE-0000-0000-0000-0000", machine: "m1" }), env, db)).status).toBe(404);
    await handle(post(`/v1/admin/keys/${k}/revoke`, {}, "admin-secret"), env, db);
    expect((await handle(post("/v1/activate", { key: k, machine: "m1" }), env, db)).status).toBe(410);
    const bad = new Request("https://x/v1/activate", { method: "POST", body: "{not json" });
    expect((await handle(bad, env, db)).status).toBe(400);
    expect((await handle(post("/v1/activate", { key: k }), env, db)).status).toBe(400);
  });
  it("key lookup ignores case and surrounding spaces", async () => {
    const db = new MemoryDb();
    const k = await create(db);
    expect((await handle(post("/v1/activate", { key: `  ${k.toLowerCase()} `, machine: "m1" }), env, db)).status).toBe(200);
  });
});

describe("check and reset", () => {
  it("active on the bound machine, 409 elsewhere, 410 after revoke", async () => {
    const db = new MemoryDb();
    const k = await create(db);
    await handle(post("/v1/activate", { key: k, machine: "m1" }), env, db);
    const ok = await handle(post("/v1/check", { key: k, machine: "m1" }), env, db);
    expect(await ok.json()).toEqual({ status: "active" });
    expect((await db.get(k))!.last_seen_at).not.toBeNull();
    expect((await handle(post("/v1/check", { key: k, machine: "m2" }), env, db)).status).toBe(409);
    await handle(post(`/v1/admin/keys/${k}/revoke`, {}, "admin-secret"), env, db);
    expect((await handle(post("/v1/check", { key: k, machine: "m1" }), env, db)).status).toBe(410);
  });
  it("reset frees the key for a new machine and reactivates a revoked key", async () => {
    const db = new MemoryDb();
    const k = await create(db);
    await handle(post("/v1/activate", { key: k, machine: "m1" }), env, db);
    await handle(post(`/v1/admin/keys/${k}/revoke`, {}, "admin-secret"), env, db);
    await handle(post(`/v1/admin/keys/${k}/reset`, {}, "admin-secret"), env, db);
    expect((await handle(post("/v1/activate", { key: k, machine: "m2" }), env, db)).status).toBe(200);
    expect((await handle(post("/v1/check", { key: k, machine: "m1" }), env, db)).status).toBe(409);
  });
  it("unknown routes are 404", async () => {
    expect((await handle(get("/nope"), env, new MemoryDb())).status).toBe(404);
  });
});
```

- [ ] **Step 4: Run to see them fail**

Run: `cd license-server && npx vitest run`
Expected: FAIL, "Cannot find module '../src/core'".

- [ ] **Step 5: Write `src/core.ts`**

```ts
import type { Db, KeyRow } from "./db";

export type CoreEnv = { ADMIN_TOKEN: string; LICENSE_SIGNING_KEY: string };

const ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

export function newKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(10));      // 80 bits
  let bits = 0n;
  for (const b of bytes) bits = (bits << 8n) | BigInt(b);
  let s = "";
  for (let i = 0; i < 16; i++) { s = ALPHABET[Number(bits & 31n)] + s; bits >>= 5n; }
  return `AE-${s.slice(0, 4)}-${s.slice(4, 8)}-${s.slice(8, 12)}-${s.slice(12, 16)}`;
}

const normKey = (k: unknown) => (typeof k === "string" ? k.trim().toUpperCase() : "");

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function b64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromB64(s: string): Uint8Array {
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
}

let cachedKey: { raw: string; key: CryptoKey } | null = null;
async function signingKey(env: CoreEnv): Promise<CryptoKey> {
  if (cachedKey?.raw !== env.LICENSE_SIGNING_KEY) {
    const key = await crypto.subtle.importKey("pkcs8", fromB64(env.LICENSE_SIGNING_KEY), { name: "Ed25519" }, false, ["sign"]);
    cachedKey = { raw: env.LICENSE_SIGNING_KEY, key };
  }
  return cachedKey.key;
}

export async function signLicense(env: CoreEnv, row: KeyRow, machine: string, now: Date): Promise<string> {
  const payload = b64url(new TextEncoder().encode(JSON.stringify({
    key: row.key, machine, name: row.name, iat: Math.floor(now.getTime() / 1000),
  })));
  const sig = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, await signingKey(env), new TextEncoder().encode(payload)));
  return `${payload}.${b64url(sig)}`;
}

function sameToken(a: string, b: string): boolean {
  const x = new TextEncoder().encode(a), y = new TextEncoder().encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

async function body(req: Request): Promise<Record<string, unknown> | null> {
  try { const b = await req.json(); return b && typeof b === "object" ? (b as Record<string, unknown>) : null; }
  catch { return null; }
}

function stateError(row: KeyRow | null, machine: string): Response | null {
  if (!row) return json(404, { error: "invalid" });
  if (row.status === "revoked") return json(410, { error: "revoked" });
  if (row.machine && row.machine !== machine) return json(409, { error: "used_elsewhere" });
  return null;
}

export async function handle(req: Request, env: CoreEnv, db: Db, now: () => Date = () => new Date()): Promise<Response> {
  const url = new URL(req.url);
  const path = url.pathname.replace(/\/+$/, "");

  if (req.method === "POST" && (path === "/v1/activate" || path === "/v1/check")) {
    const b = await body(req);
    const key = normKey(b?.key);
    const machine = typeof b?.machine === "string" ? b.machine.trim() : "";
    if (!key || !machine) return json(400, { error: "bad_request" });
    const row = await db.get(key);
    const err = stateError(row, machine);
    if (err) return err;
    const t = now().toISOString();
    if (path === "/v1/check") {
      if (!row!.machine) return json(404, { error: "invalid" });   // never activated: the app's token can't be ours
      await db.update(key, { last_seen_at: t });
      return json(200, { status: "active" });
    }
    const version = typeof b?.app_version === "string" ? b.app_version.slice(0, 32) : null;
    if (!row!.machine) await db.update(key, { machine, activated_at: t, last_seen_at: t, app_version: version });
    else await db.update(key, { last_seen_at: t, app_version: version });
    return json(200, { license: await signLicense(env, row!, machine, now()) });
  }

  if (path.startsWith("/v1/admin/")) {
    const auth = req.headers.get("authorization") ?? "";
    if (!env.ADMIN_TOKEN || !sameToken(auth, `Bearer ${env.ADMIN_TOKEN}`)) return json(401, { error: "unauthorized" });
    if (path === "/v1/admin/keys" && req.method === "GET") return json(200, { keys: await db.list() });
    if (path === "/v1/admin/keys" && req.method === "POST") {
      const b = await body(req);
      const name = typeof b?.name === "string" ? b.name.trim() : "";
      if (!name) return json(400, { error: "bad_request" });
      const row: KeyRow = { key: newKey(), name: name.slice(0, 200), note: typeof b?.note === "string" ? b.note.slice(0, 1000) : "",
        created_at: now().toISOString(), machine: null, activated_at: null, last_seen_at: null, app_version: null, status: "active" };
      await db.insert(row);
      return json(200, { key: row.key });
    }
    const m = path.match(/^\/v1\/admin\/keys\/([^/]+)\/(revoke|reset)$/);
    if (m && req.method === "POST") {
      const key = normKey(decodeURIComponent(m[1]));
      if (!(await db.get(key))) return json(404, { error: "invalid" });
      await db.update(key, m[2] === "revoke" ? { status: "revoked" } : { status: "active", machine: null, activated_at: null });
      return json(200, { ok: true });
    }
  }
  return json(404, { error: "not_found" });
}
```

- [ ] **Step 6: Write `scripts/keygen.mjs`**

```js
// Prints a new Ed25519 pair. Private key -> `wrangler secret put LICENSE_SIGNING_KEY`; public key -> app/src-tauri/license.json.
const kp = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const priv = Buffer.from(await crypto.subtle.exportKey("pkcs8", kp.privateKey)).toString("base64");
const pub = Buffer.from(await crypto.subtle.exportKey("raw", kp.publicKey)).toString("base64");
console.log("PRIVATE (secret, paste into wrangler, keep in your password manager):\n" + priv);
console.log("\nPUBLIC (goes into app/src-tauri/license.json \"pubkey\"):\n" + pub);
```

- [ ] **Step 7: Run tests**

Run: `cd license-server && npx vitest run && npx tsc`
Expected: all PASS, tsc clean.

- [ ] **Step 8: Commit**

```bash
git add license-server .gitignore
git commit -m "feat(license-server): key/token core with in-memory tests"
```

---

### Task 2: Worker entry, D1 migration, deploy docs

**Files:**
- Create: `license-server/src/index.ts`, `license-server/wrangler.toml`, `license-server/migrations/0001_init.sql`, `license-server/README.md`

**Interfaces:**
- Consumes: `handle`, `CoreEnv` from `src/core.ts`; `D1Db` from `src/db.ts`

- [ ] **Step 1: Write `migrations/0001_init.sql`**

```sql
CREATE TABLE keys (
  key TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  machine TEXT,
  activated_at TEXT,
  last_seen_at TEXT,
  app_version TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked'))
);
```

- [ ] **Step 2: Write `src/index.ts` and `wrangler.toml`**

```ts
import { handle, type CoreEnv } from "./core";
import { D1Db } from "./db";

type Env = CoreEnv & { DB: D1Database };

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    try {
      return await handle(req, env, new D1Db(env.DB));
    } catch {
      return new Response(JSON.stringify({ error: "server" }), { status: 500, headers: { "content-type": "application/json" } });
    }
  },
};
```
```toml
name = "autoedit-license"
main = "src/index.ts"
compatibility_date = "2026-11-01"

[[d1_databases]]
binding = "DB"
database_name = "autoedit-license"
database_id = "REPLACE_AFTER_d1_create"
migrations_dir = "migrations"
```
The `database_id` value is filled in during the user's one-time deploy (README step 3). Wrangler prints it.

- [ ] **Step 3: Verify the bundle builds**

Run: `cd license-server && npx wrangler deploy --dry-run --outdir /tmp/autoedit-license-dry`
Expected: "--dry-run: exiting now." with no type errors. No Cloudflare login is needed for a dry run.

- [ ] **Step 4: Write `README.md`**

Write it in Vietnamese. The one-time setup is:
1. `cd license-server && npm install`
2. `npx wrangler login`
3. `npx wrangler d1 create autoedit-license`, then paste the printed `database_id` into `wrangler.toml`.
4. `npm run migrate`
5. `npm run keygen`. Save both values in a password manager.
6. `npx wrangler secret put LICENSE_SIGNING_KEY` (paste PRIVATE).
7. `openssl rand -hex 32` → `npx wrangler secret put ADMIN_TOKEN`
8. `npm run deploy`, then note the `https://autoedit-license.<subdomain>.workers.dev` URL.
9. Put `url` and `pubkey` into `app/src-tauri/license.json` and commit; both are public.
10. `cd ../license-admin && uv run license-admin setup` (URL + admin token).

Daily use: `uv run license-admin create "Tên khách"`, `list`, `revoke <key>`, `reset <key>`.

Also cover, in a short section:
- Losing the signing key means every app build must be rebuilt with a new public key, and every customer reactivates.
- Losing the admin token: set a new one with `wrangler secret put ADMIN_TOKEN`.

- [ ] **Step 5: Commit**

```bash
git add license-server
git commit -m "feat(license-server): worker entry, D1 migration, deploy guide"
```

---

### Task 3: Admin CLI

**Files:**
- Create:
  - `license-admin/pyproject.toml`
  - `license-admin/license_admin/__init__.py`, `license-admin/license_admin/cli.py`
  - `license-admin/tests/test_cli.py`

**Interfaces:**
- Consumes: the admin endpoints from Global Constraints.
- Produces:
  - Console script `license-admin`.
  - `main(argv: list[str] | None = None) -> int`.
  - Config path `~/.autoedit-license/config.json`, overridable with env `AUTOEDIT_LICENSE_CONFIG` (tests use it).

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "license-admin"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.scripts]
license-admin = "license_admin.cli:main"

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["license_admin"]
```
`license_admin/__init__.py` is empty.

- [ ] **Step 2: Write the failing tests `tests/test_cli.py`**

```python
import json
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from license_admin import cli


class Fake:
    def __init__(self):
        self.requests = []
        self.keys = [{"key": "AE-AAAA-BBBB-CCCC-DDDD", "name": "Shop A", "note": "", "status": "active",
                      "machine": "0123456789abcdef0123456789abcdef", "activated_at": "2026-11-21T10:00:00Z",
                      "last_seen_at": "2026-11-21T11:00:00Z", "created_at": "2026-11-21T09:00:00Z"}]

    def __enter__(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _handle(self, method):
                n = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(n) if n else b""
                fake.requests.append({"method": method, "path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()},
                                      "body": json.loads(raw) if raw else None})
                if self.headers.get("authorization") != "Bearer tok":
                    return self._reply(401, {"error": "unauthorized"})
                if method == "GET" and self.path == "/v1/admin/keys":
                    return self._reply(200, {"keys": fake.keys})
                if method == "POST" and self.path == "/v1/admin/keys":
                    return self._reply(200, {"key": "AE-NEW0-0000-0000-0001"})
                if method == "POST" and self.path.endswith(("/revoke", "/reset")):
                    if "AE-AAAA-BBBB-CCCC-DDDD" in self.path:
                        return self._reply(200, {"ok": True})
                    return self._reply(404, {"error": "invalid"})
                return self._reply(404, {"error": "not_found"})

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    p = tmp_path / "cfg" / "config.json"
    monkeypatch.setenv("AUTOEDIT_LICENSE_CONFIG", str(p))
    return p


def write_cfg(p, url, token="tok"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"url": url, "admin_token": token}))


def test_setup_writes_private_config(cfg, monkeypatch):
    answers = iter(["https://lic.example.workers.dev/"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: "tok")
    assert cli.main(["setup"]) == 0
    data = json.loads(cfg.read_text())
    assert data == {"url": "https://lic.example.workers.dev", "admin_token": "tok"}
    if os.name == "posix":
        assert stat.S_IMODE(cfg.stat().st_mode) == 0o600


def test_create_prints_key_and_sends_auth_and_user_agent(cfg, capsys):
    with Fake() as f:
        write_cfg(cfg, f.url)
        assert cli.main(["create", "Shop B", "--note", "zalo 09"]) == 0
        r = f.requests[0]
        assert r["body"] == {"name": "Shop B", "note": "zalo 09"}
        assert r["headers"]["user-agent"].startswith("AutoEdit-License-Admin/")
    assert "AE-NEW0-0000-0000-0001" in capsys.readouterr().out


def test_list_shows_table(cfg, capsys):
    with Fake() as f:
        write_cfg(cfg, f.url)
        assert cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "AE-AAAA-BBBB-CCCC-DDDD" in out and "Shop A" in out and "active" in out and "01234567" in out


def test_revoke_and_reset(cfg, capsys):
    with Fake() as f:
        write_cfg(cfg, f.url)
        assert cli.main(["revoke", "ae-aaaa-bbbb-cccc-dddd"]) == 0
        assert cli.main(["reset", "AE-AAAA-BBBB-CCCC-DDDD"]) == 0
        assert [r["path"] for r in f.requests] == ["/v1/admin/keys/AE-AAAA-BBBB-CCCC-DDDD/revoke",
                                                   "/v1/admin/keys/AE-AAAA-BBBB-CCCC-DDDD/reset"]


def test_unknown_key_and_bad_token_exit_nonzero(cfg, capsys):
    with Fake() as f:
        write_cfg(cfg, f.url)
        assert cli.main(["revoke", "AE-ZZZZ-ZZZZ-ZZZZ-ZZZZ"]) == 1
        assert "Không có key" in capsys.readouterr().err
        write_cfg(cfg, f.url, token="wrong")
        assert cli.main(["list"]) == 1
        assert "Admin token sai" in capsys.readouterr().err


def test_missing_config(cfg, capsys):
    assert cli.main(["list"]) == 1
    assert "license-admin setup" in capsys.readouterr().err
```

- [ ] **Step 3: Run to see them fail**

Run: `cd license-admin && uv run pytest -q`
Expected: FAIL, "cannot import name 'cli'".

- [ ] **Step 4: Write `license_admin/cli.py`**

```python
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "AutoEdit-License-Admin/1"


def config_path() -> Path:
    return Path(os.environ.get("AUTOEDIT_LICENSE_CONFIG") or Path.home() / ".autoedit-license" / "config.json")


def load_config() -> dict:
    p = config_path()
    if not p.exists():
        raise SystemExit("Chưa cấu hình. Chạy: license-admin setup")
    return json.loads(p.read_text(encoding="utf-8"))


class ApiError(Exception):
    pass


def call(cfg: dict, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(cfg["url"] + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {cfg['admin_token']}")
    req.add_header("User-Agent", USER_AGENT)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ApiError("Admin token sai. Chạy lại: license-admin setup") from None
        if e.code == 404:
            raise ApiError("Không có key này") from None
        raise ApiError(f"Máy chủ trả lỗi {e.code}") from None
    except urllib.error.URLError as e:
        raise ApiError(f"Không kết nối được máy chủ: {e.reason}") from None


def norm(key: str) -> str:
    return key.strip().upper()


def cmd_setup(_a) -> int:
    url = input("URL của Worker (https://...workers.dev): ").strip().rstrip("/")
    token = getpass.getpass("Admin token: ").strip()
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"url": url, "admin_token": token}, f)
    os.chmod(p, 0o600)
    print(f"Đã lưu cấu hình vào {p}")
    return 0


def cmd_create(a) -> int:
    r = call(load_config(), "POST", "/v1/admin/keys", {"name": a.name, "note": a.note or ""})
    print(r["key"])
    return 0


def cmd_list(_a) -> int:
    keys = call(load_config(), "GET", "/v1/admin/keys")["keys"]
    rows = [("KEY", "KHÁCH", "TRẠNG THÁI", "MÁY", "KÍCH HOẠT", "LẦN CUỐI")]
    for k in keys:
        rows.append((k["key"], k["name"], k["status"], (k.get("machine") or "-")[:8],
                     (k.get("activated_at") or "-")[:10], (k.get("last_seen_at") or "-")[:16].replace("T", " ")))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))
    return 0


def cmd_action(a) -> int:
    call(load_config(), "POST", f"/v1/admin/keys/{urllib.parse.quote(norm(a.key))}/{a.cmd}", {})
    print("Đã thu hồi" if a.cmd == "revoke" else "Đã reset: key kích hoạt lại được trên một máy mới")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="license-admin")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup").set_defaults(fn=cmd_setup)
    c = sub.add_parser("create")
    c.add_argument("name")
    c.add_argument("--note")
    c.set_defaults(fn=cmd_create)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    for name in ("revoke", "reset"):
        x = sub.add_parser(name)
        x.add_argument("key")
        x.set_defaults(fn=cmd_action)
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except ApiError as e:
        print(str(e), file=sys.stderr)
        return 1
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests**

Run: `cd license-admin && uv run pytest -q`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add license-admin
git commit -m "feat(license-admin): create/list/revoke/reset CLI"
```

---

### Task 4: Rust license core (machine hash, token verification, HTTP calls)

**Files:**
- Create: `app/src-tauri/src/license.rs`, `app/src-tauri/license.json`
- Modify:
  - `app/src-tauri/Cargo.toml`: add `ed25519-dalek = "2"`, `sha2 = "0.10"`, `base64 = "0.22"`, `reqwest = { version = "0.13", features = ["json"] }`
  - `app/src-tauri/build.rs`
  - `app/src-tauri/src/lib.rs`: add `mod license;`
  - `app/src-tauri/src/secrets.rs`: add `pub const LICENSE_ACCOUNT: &str = "license";`
- Test: unit tests inside `license.rs`

The `reqwest` line must reuse the version already in Cargo.lock. Check with `cargo tree -d | grep reqwest`, which should show no duplicate. If 0.13 has no `json` feature, use `serde_json` on `.text()`.

**Interfaces:**
- Produces:
  - `pub struct License { pub key: String, pub machine: String, pub name: String, pub iat: i64 }`
  - `pub fn verify_token(token: &str, pubkey_b64: &str, machine: &str) -> Result<License, String>`
  - `pub fn machine_hash() -> Result<String, String>`
  - `pub fn hash_platform_id(id: &str) -> String`
  - `pub enum Remote { Ok(String /*token or "active"*/), Invalid, Used, Revoked, Offline }`
  - `pub async fn activate(url: &str, key: &str, machine: &str, version: &str) -> Remote`
  - `pub async fn check(url: &str, key: &str, machine: &str) -> Remote`
  - `pub fn code(r: &Remote) -> &'static str` maps to `LICENSE_INVALID`/`LICENSE_USED`/`LICENSE_REVOKED`/`LICENSE_OFFLINE`.
  - `pub const URL: &str` and `pub const PUBKEY: &str` come from `env!("AUTOEDIT_LICENSE_URL")` and `env!("AUTOEDIT_LICENSE_PUBKEY")`, set by build.rs.

- [ ] **Step 1: Write `license.json` and `build.rs`**

`app/src-tauri/license.json`:
```json
{ "url": "", "pubkey": "" }
```
`build.rs`: keep the existing `tauri_build::build()` call and add, before it:
```rust
fn license_config() {
    println!("cargo:rerun-if-changed=license.json");
    let raw = std::fs::read_to_string("license.json").expect("app/src-tauri/license.json is missing");
    let v: serde_json::Value = serde_json::from_str(&raw).expect("license.json is not valid JSON");
    let url = v["url"].as_str().unwrap_or("").trim_end_matches('/').to_string();
    let pubkey = v["pubkey"].as_str().unwrap_or("").to_string();
    if std::env::var("PROFILE").as_deref() == Ok("release") && (url.is_empty() || pubkey.is_empty()) {
        panic!("license.json has no url/pubkey: deploy license-server first (license-server/README.md)");
    }
    println!("cargo:rustc-env=AUTOEDIT_LICENSE_URL={url}");
    println!("cargo:rustc-env=AUTOEDIT_LICENSE_PUBKEY={pubkey}");
}
```
Call `license_config();` first in `main()`. Add `serde_json = "1"` under `[build-dependencies]` in Cargo.toml.

- [ ] **Step 2: Write the failing tests at the bottom of `license.rs`**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use base64::Engine;
    use ed25519_dalek::{Signer, SigningKey};

    fn keypair() -> (SigningKey, String) {
        let sk = SigningKey::from_bytes(&[7u8; 32]);
        let pk = base64::engine::general_purpose::STANDARD.encode(sk.verifying_key().to_bytes());
        (sk, pk)
    }

    fn token(sk: &SigningKey, payload: &str) -> String {
        let p = B64URL.encode(payload.as_bytes());
        let sig = sk.sign(p.as_bytes());
        format!("{p}.{}", B64URL.encode(sig.to_bytes()))
    }

    const PAYLOAD: &str = r#"{"key":"AE-AAAA-BBBB-CCCC-DDDD","machine":"m1","name":"Shop A","iat":1763700000}"#;

    #[test]
    fn verifies_good_token_for_this_machine() {
        let (sk, pk) = keypair();
        let l = verify_token(&token(&sk, PAYLOAD), &pk, "m1").unwrap();
        assert_eq!(l.key, "AE-AAAA-BBBB-CCCC-DDDD");
        assert_eq!(l.name, "Shop A");
    }

    #[test]
    fn rejects_other_machine_bad_signature_and_garbage() {
        let (sk, pk) = keypair();
        let t = token(&sk, PAYLOAD);
        assert!(verify_token(&t, &pk, "m2").is_err());
        let other = SigningKey::from_bytes(&[9u8; 32]);
        assert!(verify_token(&token(&other, PAYLOAD), &pk, "m1").is_err());
        let tampered = token(&sk, PAYLOAD).replacen('e', "f", 1);
        assert!(verify_token(&tampered, &pk, "m1").is_err());
        assert!(verify_token("garbage", &pk, "m1").is_err());
        assert!(verify_token(&t, "", "m1").is_err());
    }

    #[test]
    fn platform_hash_is_stable_32_hex() {
        let a = hash_platform_id("ABC-123");
        assert_eq!(a, hash_platform_id("ABC-123"));
        assert_ne!(a, hash_platform_id("ABC-124"));
        assert_eq!(a.len(), 32);
        assert!(a.chars().all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()));
    }

    #[test]
    fn parses_ioreg_and_reg_output() {
        let ioreg = "  |   \"IOPlatformUUID\" = \"1234ABCD-0000-1111-2222-333344445555\"\n";
        assert_eq!(parse_ioreg(ioreg).as_deref(), Some("1234ABCD-0000-1111-2222-333344445555"));
        let reg = "\r\nHKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography\r\n    MachineGuid    REG_SZ    9f1c-aa\r\n";
        assert_eq!(parse_reg(reg).as_deref(), Some("9f1c-aa"));
        assert_eq!(parse_ioreg("nothing"), None);
    }

    #[test]
    fn this_machine_has_a_hash() {
        assert_eq!(machine_hash().unwrap().len(), 32);
    }

    #[test]
    fn status_mapping() {
        assert!(matches!(from_status(404, ""), Remote::Invalid));
        assert!(matches!(from_status(409, ""), Remote::Used));
        assert!(matches!(from_status(410, ""), Remote::Revoked));
        assert!(matches!(from_status(500, ""), Remote::Offline));
        assert!(matches!(from_status(200, r#"{"license":"t.s"}"#), Remote::Ok(ref t) if t == "t.s"));
        assert!(matches!(from_status(200, r#"{"status":"active"}"#), Remote::Ok(ref s) if s == "active"));
        assert_eq!(code(&Remote::Used), "LICENSE_USED");
    }

    #[tokio::test]
    async fn unreachable_server_is_offline() {
        assert!(matches!(activate("http://127.0.0.1:9", "AE-X", "m1", "0").await, Remote::Offline));
    }
}
```
If `tokio` isn't a direct dev-dependency, add `tokio = { version = "1", features = ["macros", "rt"] }` under `[dev-dependencies]`. It is already in the tree via tauri.

- [ ] **Step 3: Run to see them fail**

Run: `cd app/src-tauri && cargo test license`
Expected: compile errors for the missing functions.

- [ ] **Step 4: Write the implementation (top of `license.rs`)**

```rust
//! License gate: machine hash, offline token verification, activation API calls (spec 2026-11-21).
use base64::Engine;
use base64::engine::general_purpose::{STANDARD, URL_SAFE_NO_PAD as B64URL_ENGINE};
use ed25519_dalek::{Signature, VerifyingKey};
use serde::Deserialize;
use sha2::{Digest, Sha256};

pub const URL: &str = env!("AUTOEDIT_LICENSE_URL");
pub const PUBKEY: &str = env!("AUTOEDIT_LICENSE_PUBKEY");
#[allow(dead_code)]
const B64URL: base64::engine::GeneralPurpose = B64URL_ENGINE;
const USER_AGENT: &str = concat!("AutoEdit/", env!("CARGO_PKG_VERSION"));

#[derive(Debug, Clone, Deserialize)]
pub struct License {
    pub key: String,
    pub machine: String,
    pub name: String,
    pub iat: i64,
}

pub fn verify_token(token: &str, pubkey_b64: &str, machine: &str) -> Result<License, String> {
    let (payload, sig) = token.trim().split_once('.').ok_or("malformed")?;
    let pk: [u8; 32] = STANDARD.decode(pubkey_b64).map_err(|_| "bad pubkey")?.try_into().map_err(|_| "bad pubkey")?;
    let vk = VerifyingKey::from_bytes(&pk).map_err(|_| "bad pubkey")?;
    let sig = Signature::from_slice(&B64URL.decode(sig).map_err(|_| "malformed")?).map_err(|_| "malformed")?;
    vk.verify_strict(payload.as_bytes(), &sig).map_err(|_| "bad signature")?;
    let l: License = serde_json::from_slice(&B64URL.decode(payload).map_err(|_| "malformed")?).map_err(|_| "malformed")?;
    if l.machine != machine {
        return Err("other machine".into());
    }
    Ok(l)
}

pub fn hash_platform_id(id: &str) -> String {
    let d = Sha256::digest(format!("autoedit:{}", id.trim()).as_bytes());
    d.iter().take(16).map(|b| format!("{b:02x}")).collect()
}

fn parse_ioreg(out: &str) -> Option<String> {
    let line = out.lines().find(|l| l.contains("\"IOPlatformUUID\""))?;
    let v = line.split('=').nth(1)?.trim().trim_matches('"');
    (!v.is_empty()).then(|| v.to_string())
}

fn parse_reg(out: &str) -> Option<String> {
    let line = out.lines().find(|l| l.contains("MachineGuid"))?;
    line.split("REG_SZ").nth(1).map(|s| s.trim().to_string()).filter(|s| !s.is_empty())
}

pub fn machine_hash() -> Result<String, String> {
    #[cfg(target_os = "macos")]
    let id = {
        let o = std::process::Command::new("/usr/sbin/ioreg").args(["-rd1", "-c", "IOPlatformExpertDevice"])
            .output().map_err(|e| e.to_string())?;
        parse_ioreg(&String::from_utf8_lossy(&o.stdout))
    };
    #[cfg(target_os = "windows")]
    let id = {
        use std::os::windows::process::CommandExt;
        let o = std::process::Command::new("reg")
            .args(["query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"])
            .creation_flags(0x0800_0000)               // CREATE_NO_WINDOW
            .output().map_err(|e| e.to_string())?;
        parse_reg(&String::from_utf8_lossy(&o.stdout))
    };
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    let id = std::fs::read_to_string("/etc/machine-id").ok();
    id.map(|i| hash_platform_id(&i)).ok_or_else(|| "Không đọc được mã máy".into())
}

#[derive(Debug)]
pub enum Remote { Ok(String), Invalid, Used, Revoked, Offline }

pub fn code(r: &Remote) -> &'static str {
    match r {
        Remote::Invalid => "LICENSE_INVALID",
        Remote::Used => "LICENSE_USED",
        Remote::Revoked => "LICENSE_REVOKED",
        Remote::Offline | Remote::Ok(_) => "LICENSE_OFFLINE",
    }
}

fn from_status(status: u16, body: &str) -> Remote {
    match status {
        200 => {
            let v: serde_json::Value = serde_json::from_str(body).unwrap_or_default();
            match v["license"].as_str().or(v["status"].as_str()) {
                Some(s) => Remote::Ok(s.to_string()),
                None => Remote::Offline,
            }
        }
        404 => Remote::Invalid,
        409 => Remote::Used,
        410 => Remote::Revoked,
        _ => Remote::Offline,
    }
}

async fn post(url: &str, path: &str, body: serde_json::Value) -> Remote {
    if url.is_empty() {
        return Remote::Offline;
    }
    let client = match reqwest::Client::builder().user_agent(USER_AGENT).timeout(std::time::Duration::from_secs(15)).build() {
        Ok(c) => c,
        Err(_) => return Remote::Offline,
    };
    match client.post(format!("{url}{path}")).json(&body).send().await {
        Ok(r) => {
            let s = r.status().as_u16();
            from_status(s, &r.text().await.unwrap_or_default())
        }
        Err(_) => Remote::Offline,
    }
}

pub async fn activate(url: &str, key: &str, machine: &str, version: &str) -> Remote {
    post(url, "/v1/activate", serde_json::json!({"key": key.trim(), "machine": machine, "app_version": version})).await
}

pub async fn check(url: &str, key: &str, machine: &str) -> Remote {
    post(url, "/v1/check", serde_json::json!({"key": key, "machine": machine})).await
}
```
Make the `B64URL` alias tidy: drop the `#[allow]` and the alias and use `URL_SAFE_NO_PAD` directly in both code and tests, as long as tests still compile with `use super::*`.

- [ ] **Step 5: Run tests and clippy**

Run: `cd app/src-tauri && cargo test license && cargo clippy --all-targets -- -D warnings`
Expected: PASS, no warnings.

- [ ] **Step 6: Commit**

```bash
git add app/src-tauri
git commit -m "feat(app): license core: machine hash, token verify, activation API client"
```

---

### Task 5: Rust gate, commands, background revocation check

**Files:**
- Modify: `app/src-tauri/src/license.rs` (add `Gate`), `app/src-tauri/src/commands.rs`, `app/src-tauri/src/lib.rs`
- Test: unit tests in `license.rs`

**Interfaces:**
- Consumes: Task 4 functions; `secrets::{SecretStore, LICENSE_ACCOUNT}`.
- Produces:
  - `pub struct Gate { licensed: AtomicBool, license: Mutex<Option<License>>, machine: String }`, with:
    - `Gate::load(store: &dyn SecretStore, pubkey: &str) -> Gate`
    - `is_licensed()`
    - `set(store, token, pubkey) -> Result<License, String>`
    - `revoke(store)`
    - `key() -> Option<String>`
    - `machine() -> &str`
  - `pub const OPEN_COMMANDS: &[&str] = &["license_status", "license_activate", "kill_all_jobs"]`
  - `pub fn allowed(cmd: &str, licensed: bool) -> bool`
  - Tauri commands:
    - `license_status() -> {licensed: bool, name: Option<String>}`
    - `license_activate(key) -> Result<{licensed:true,name}, String /*code*/>`
  - Event `"license-revoked"` with payload `{reason: "LICENSE_REVOKED"|"LICENSE_USED"|"LICENSE_INVALID"}`.

- [ ] **Step 1: Write the failing tests (append to `license.rs` tests)**

```rust
    use crate::secrets::{MemoryStore, SecretStore, LICENSE_ACCOUNT};

    fn gate_with(store: &MemoryStore, pk: &str, machine: &str) -> Gate {
        Gate::load_for(store, pk, machine.to_string())
    }

    #[test]
    fn gate_unlicensed_without_token_and_licensed_with_valid_one() {
        let (sk, pk) = keypair();
        let store = MemoryStore::default();
        let g = gate_with(&store, &pk, "m1");
        assert!(!g.is_licensed());
        g.set(&store, &token(&sk, PAYLOAD), &pk).unwrap();
        assert!(g.is_licensed());
        assert_eq!(store.get(LICENSE_ACCOUNT).unwrap(), token(&sk, PAYLOAD));
        assert!(gate_with(&store, &pk, "m1").is_licensed());          // next launch, offline
        assert!(!gate_with(&store, &pk, "m2").is_licensed());         // copied Keychain to another machine
    }

    #[test]
    fn gate_set_rejects_token_for_other_machine_and_revoke_clears() {
        let (sk, pk) = keypair();
        let store = MemoryStore::default();
        let g = gate_with(&store, &pk, "m2");
        assert!(g.set(&store, &token(&sk, PAYLOAD), &pk).is_err());
        assert!(store.get(LICENSE_ACCOUNT).is_none());
        let g1 = gate_with(&store, &pk, "m1");
        g1.set(&store, &token(&sk, PAYLOAD), &pk).unwrap();
        g1.revoke(&store);
        assert!(!g1.is_licensed() && store.get(LICENSE_ACCOUNT).is_none() && g1.key().is_none());
    }

    #[test]
    fn only_open_commands_pass_while_unlicensed() {
        assert!(allowed("license_status", false));
        assert!(allowed("license_activate", false));
        assert!(!allowed("engine_run", false));
        assert!(!allowed("create_project", false));
        assert!(allowed("engine_run", true));
    }
```

- [ ] **Step 2: Run to see them fail**

Run: `cd app/src-tauri && cargo test license`
Expected: compile errors, because `Gate` is not defined.

- [ ] **Step 3: Implement `Gate` and `allowed` in `license.rs`**

```rust
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use crate::secrets::{SecretStore, LICENSE_ACCOUNT};

pub const OPEN_COMMANDS: &[&str] = &["license_status", "license_activate", "kill_all_jobs"];

pub fn allowed(cmd: &str, licensed: bool) -> bool {
    licensed || OPEN_COMMANDS.contains(&cmd)
}

pub struct Gate {
    licensed: AtomicBool,
    license: Mutex<Option<License>>,
    machine: String,
}

impl Gate {
    pub fn load(store: &dyn SecretStore, pubkey: &str) -> Gate {
        let machine = machine_hash().unwrap_or_default();
        Self::load_for(store, pubkey, machine)
    }

    pub fn load_for(store: &dyn SecretStore, pubkey: &str, machine: String) -> Gate {
        let lic = store.get(LICENSE_ACCOUNT).and_then(|t| verify_token(&t, pubkey, &machine).ok());
        let dev = cfg!(debug_assertions) && std::env::var("AUTOEDIT_LICENSE_DEV").as_deref() == Ok("1");
        Gate { licensed: AtomicBool::new(lic.is_some() || dev), license: Mutex::new(lic), machine }
    }

    pub fn is_licensed(&self) -> bool { self.licensed.load(Ordering::SeqCst) }
    pub fn machine(&self) -> &str { &self.machine }
    pub fn key(&self) -> Option<String> { self.license.lock().unwrap().as_ref().map(|l| l.key.clone()) }
    pub fn name(&self) -> Option<String> { self.license.lock().unwrap().as_ref().map(|l| l.name.clone()) }

    pub fn set(&self, store: &dyn SecretStore, token: &str, pubkey: &str) -> Result<License, String> {
        let l = verify_token(token, pubkey, &self.machine)?;
        store.set(LICENSE_ACCOUNT, token)?;
        *self.license.lock().unwrap() = Some(l.clone());
        self.licensed.store(true, Ordering::SeqCst);
        Ok(l)
    }

    pub fn revoke(&self, store: &dyn SecretStore) {
        let _ = store.delete(LICENSE_ACCOUNT);
        *self.license.lock().unwrap() = None;
        self.licensed.store(false, Ordering::SeqCst);
    }
}
```
Do not import `MemoryStore` outside `#[cfg(test)]`.

- [ ] **Step 4: Add the commands in `commands.rs`**

Add `pub gate: Arc<license::Gate>` to `AppState`, and construct it in `lib.rs` setup as `Arc::new(license::Gate::load(&secrets::KeyringStore, license::PUBKEY))`. Update every place that builds `AppState`, including tests.
```rust
#[tauri::command]
pub fn license_status(state: State<'_, AppState>) -> serde_json::Value {
    serde_json::json!({ "licensed": state.gate.is_licensed(), "name": state.gate.name() })
}

#[tauri::command]
pub async fn license_activate(state: State<'_, AppState>, key: String) -> Result<serde_json::Value, String> {
    let machine = state.gate.machine().to_string();
    if machine.is_empty() {
        return Err("LICENSE_OFFLINE".into());
    }
    match crate::license::activate(crate::license::URL, &key, &machine, env!("CARGO_PKG_VERSION")).await {
        crate::license::Remote::Ok(token) => {
            let l = state.gate.set(state.secrets.as_ref(), &token, crate::license::PUBKEY)
                .map_err(|_| "LICENSE_INVALID".to_string())?;
            Ok(serde_json::json!({ "licensed": true, "name": l.name }))
        }
        other => Err(crate::license::code(&other).into()),
    }
}
```
Adapt `state.secrets.as_ref()` to however `secrets` is typed in `AppState`. It is `Arc<KeyringStore>` today; pass `&*state.secrets`.

- [ ] **Step 5: Central gate and background check in `lib.rs`**

Register `commands::license_status, commands::license_activate` in `generate_handler!`, and wrap the handler:
```rust
let handler = tauri::generate_handler![ /* existing list + license_status, license_activate */ ];
// ...
.invoke_handler(move |invoke| {
    let licensed = invoke.message.webview().app_handle().state::<commands::AppState>().gate.is_licensed();
    if !license::allowed(invoke.message.command(), licensed) {
        invoke.resolver.reject("LICENSE_REQUIRED");
        return true;
    }
    handler(invoke)
})
```
Before relying on this, check the Tauri 2.12 `Invoke` API: `invoke.message.command()`, `invoke.message.webview()`, `invoke.resolver.reject()`. If any of these differ, use the equivalent accessors in that version. If no central hook is possible, call `require_license(&state)?` at the top of every non-open command, and add a test that lists every registered command name.

In `setup`, after `app.manage(...)`, spawn the check loop:
```rust
let handle = app.handle().clone();
tauri::async_runtime::spawn(async move {
    loop {
        let st = handle.state::<commands::AppState>();
        if let Some(key) = st.gate.key() {
            let r = license::check(license::URL, &key, st.gate.machine()).await;
            if matches!(r, license::Remote::Revoked | license::Remote::Used | license::Remote::Invalid) {
                st.gate.revoke(&*st.secrets);
                let _ = handle.emit("license-revoked", serde_json::json!({ "reason": license::code(&r) }));
            }
        }
        tokio::time::sleep(std::time::Duration::from_secs(6 * 3600)).await;
    }
});
```
If `tokio` is not a direct dependency, add it with `tokio = { version = "1", features = ["time"] }`. Use `tauri::Emitter` for `emit`.

- [ ] **Step 6: Run tests and clippy**

Run: `cd app/src-tauri && cargo test && cargo clippy --all-targets -- -D warnings`
Expected: all PASS, including the 47 existing tests.

- [ ] **Step 7: Commit**

```bash
git add app/src-tauri
git commit -m "feat(app): license gate on every command, activation command, 6-hourly revocation check"
```

---

### Task 6: Activation screen and boot order (UI)

**Files:**
- Create: `app/src/screens/Activate.tsx`, `app/src/screens/Activate.test.tsx`
- Modify:
  - `app/src/lib/api.ts`, `app/src/lib/types.ts`
  - `app/src/state/store.tsx`: route `{name:"activate", reason?: string}`, boot order, event listener
  - `app/src/App.tsx`: render `Activate` full-screen with no Sidebar
  - `app/src/App.test.tsx` and any test whose invoke mock must now answer `license_status`
  - `app/src/styles.css`

**Interfaces:**
- Consumes: the `license_status` and `license_activate` commands and the `license-revoked` event from Task 5.
- Produces:
  - `api.licenseStatus(): Promise<{licensed: boolean; name: string | null}>`
  - `api.licenseActivate(key: string): Promise<{licensed: true; name: string}>`, which rejects with a code string.
  - `licenseMessage(code: string): string` in `app/src/lib/license.ts`.

- [ ] **Step 1: API and messages**

`app/src/lib/api.ts`:
```ts
export const licenseStatus = () => invoke<{ licensed: boolean; name: string | null }>("license_status");
export const licenseActivate = (key: string) => invoke<{ licensed: true; name: string }>("license_activate", { key });
```
`app/src/lib/license.ts`:
```ts
const MESSAGES: Record<string, string> = {
  LICENSE_INVALID: "Key không đúng",
  LICENSE_USED: "Key đã được kích hoạt trên máy khác. Liên hệ người bán để được hỗ trợ.",
  LICENSE_REVOKED: "Key đã bị thu hồi",
  LICENSE_OFFLINE: "Không kết nối được máy chủ kích hoạt, kiểm tra mạng rồi thử lại",
};
export const licenseMessage = (code: unknown) => MESSAGES[String(code)] ?? MESSAGES.LICENSE_OFFLINE;
```

- [ ] **Step 2: Write the failing test `Activate.test.tsx`**

Follow the invoke-mocking pattern in `app/src/screens/Onboarding.test.tsx`, using the same helpers and `@tauri-apps/api/mocks` usage. Cases:
1. It renders the title "Kích hoạt AutoEdit", a key input, and a "Kích hoạt" button that is disabled while the input is empty.
2. Typing `AE-AAAA-BBBB-CCCC-DDDD` and clicking calls `license_activate` with `{ key: "AE-AAAA-BBBB-CCCC-DDDD" }`, and on success calls the `onDone` prop.
3. When `license_activate` rejects with `"LICENSE_USED"`, it shows "Key đã được kích hoạt trên máy khác. Liên hệ người bán để được hỗ trợ." and does not call `onDone`.
4. With prop `reason="LICENSE_REVOKED"`, it shows "Key đã bị thu hồi" before any click.
5. While the request is pending the button shows "Đang kích hoạt…" and is disabled.

- [ ] **Step 3: Run to see it fail**

Run: `cd app && npx vitest run src/screens/Activate.test.tsx`
Expected: FAIL, the module is not found.

- [ ] **Step 4: Write `Activate.tsx`**

```tsx
import { useState } from "react";
import * as api from "../lib/api";
import { licenseMessage } from "../lib/license";

export default function Activate({ reason, onDone }: { reason?: string; onDone: () => void }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(reason ? licenseMessage(reason) : null);

  async function submit() {
    setBusy(true); setErr(null);
    try {
      await api.licenseActivate(key.trim());
      onDone();
    } catch (e) {
      setErr(licenseMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="activate">
      <div className="activate-card">
        <h1>Kích hoạt AutoEdit</h1>
        <p className="sub">Dán key bạn nhận được từ người bán rồi bấm Kích hoạt. Mỗi key dùng cho một máy.</p>
        <input value={key} onChange={(e) => setKey(e.target.value)} placeholder="AE-XXXX-XXXX-XXXX-XXXX"
          autoFocus spellCheck={false} onKeyDown={(e) => { if (e.key === "Enter" && key.trim() && !busy) void submit(); }} />
        {err && <div className="activate-err" role="alert">{err}</div>}
        <button className="btn primary big" disabled={!key.trim() || busy} onClick={submit}>
          {busy ? "Đang kích hoạt…" : "Kích hoạt"}
        </button>
      </div>
    </div>
  );
}
```
Add `.activate`, `.activate-card` and `.activate-err` styles in `styles.css`, matching the existing onboarding card look. Look at the `.onboard` and `.card` rules and reuse their colors and radius.

- [ ] **Step 5: Wire boot order and the revoked event**

In `store.tsx`:
- Extend `Route` with `| { name: "activate"; reason?: string }`.
- Move the body of the boot effect into a `boot` callback.
- At its start:
  ```ts
  let lic = { licensed: false };
  try { lic = await api.licenseStatus(); } catch { /* treat as unlicensed */ }
  if (!lic.licensed) { dispatch({ type: "route", route: { name: "activate" } }); return; }   // finally still marks ready
  ```
- Expose `boot` on the context.
- Add an effect that listens to the Tauri event `license-revoked` with `listen` from `@tauri-apps/api/event`, wrapped in try/catch for tests, and dispatches `{ type: "route", route: { name: "activate", reason: payload.reason } }`.

In `App.tsx`, render this before `<div className="app">` when the route is `activate`:
```tsx
if (state.route.name === "activate") return <Activate reason={state.route.reason} onDone={() => void boot()} />;
```
Destructure `boot` from `useStore()`, and add a `case "activate": return null;` in `Screen` for exhaustiveness.

Every existing test that mocks invoke for the boot path must now answer `license_status` with `{ licensed: true, name: "Test" }`. Update the shared mock helper if there is one. Add an `App.test.tsx` case: when `license_status` returns `{ licensed: false }`, the activation screen shows and `get_settings` is never called.

- [ ] **Step 6: Run all UI tests and the typecheck**

Run: `cd app && npx vitest run && npx tsc -b`
Expected: all PASS, tsc clean.

- [ ] **Step 7: Commit**

```bash
git add app/src
git commit -m "feat(app): activation screen, license-first boot, lock on revocation"
```

---

### Task 7: Build guard and release docs

**Files:**
- Modify: `scripts/build-app.sh`, `docs/RELEASE.md`

- [ ] **Step 1: Fail early in `build-app.sh`**

After `cd "$ROOT"`, add:
```bash
if ! python3 -c 'import json,sys; d=json.load(open("app/src-tauri/license.json")); sys.exit(0 if d.get("url") and d.get("pubkey") else 1)'; then
  echo "app/src-tauri/license.json chưa có url/pubkey. Làm theo license-server/README.md trước khi build bản phát hành." >&2
  exit 1
fi
```

- [ ] **Step 2: Add a "License" section to `docs/RELEASE.md`**

The section says:
- Releases require a filled `license.json` (see `license-server/README.md`).
- The signing private key and admin token live only in the password manager and as Worker secrets.
- Rotating the signing key requires a new app release, and every customer must activate again.

- [ ] **Step 3: Verify**

Run: `bash -n scripts/build-app.sh && cd app/src-tauri && cargo build` (debug, so an empty license.json is allowed).
Expected: both succeed.

- [ ] **Step 4: Commit**

```bash
git add scripts/build-app.sh docs/RELEASE.md
git commit -m "build: require license config for release builds"
```

---

## Self-review notes

**Spec coverage:**
- Worker endpoints and key/token formats: Tasks 1–2.
- D1 schema: Task 2.
- Admin CLI with setup, create, list, revoke and reset: Task 3.
- Keygen: Task 1 `scripts/keygen.mjs`. This is a deviation from the spec, which put keygen in the admin CLI; it moved because stdlib Python has no Ed25519. The spec is updated to match.
- Machine hash and offline token verification: Task 4.
- Keychain storage, Rust-enforced gate, 6-hour check and revoked event: Task 5.
- Activation screen, Vietnamese copy and boot order: Task 6.
- Release build guard and dev bypass: Task 4 (build.rs), Task 5 (`AUTOEDIT_LICENSE_DEV`) and Task 7.
- Testing per component: each task.

**Deferred, requires the user:** the Cloudflare account and the one-time deploy in README steps 1–10. Until then, release builds fail on purpose.
