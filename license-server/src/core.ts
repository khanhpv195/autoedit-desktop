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

const KEY_BODY = /^[0-9A-HJKMNP-TV-Z]{16}$/;

/** Shared with the CLI (`norm`) and the app: same vectors in all three test suites. */
export function normKey(k: unknown): string {
  if (typeof k !== "string") return "";
  const s = k.normalize("NFKC").replace(/[\s\u200B-\u200D\uFEFF]/g, "")
    .replace(/[\u2010-\u2015\u2212]/g, "-").toUpperCase();
  if (!s.startsWith("AE")) return s;
  const body = s.slice(2).replace(/^-/, "").replace(/O/g, "0").replace(/[IL]/g, "1");
  const flat = body.replace(/-/g, "");
  if (KEY_BODY.test(flat)) return `AE-${flat.slice(0, 4)}-${flat.slice(4, 8)}-${flat.slice(8, 12)}-${flat.slice(12)}`;
  return `AE-${body}`;
}

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
    // One conditional UPDATE decides the winner; never sign before it succeeds.
    if ((await db.claim(key, machine, t, version)) === 0) {
      return stateError(await db.get(key), machine) ?? json(503, { error: "retry" });
    }
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
