import { describe, expect, it, beforeAll } from "vitest";
import { handle, newKey, normKey, type CoreEnv } from "../src/core";
import { MemoryDb } from "../src/db";
import vectors from "./key-vectors.json";

let env: CoreEnv;
let pub: CryptoKey;

beforeAll(async () => {
  const kp = (await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"])) as CryptoKeyPair;
  const pkcs8 = new Uint8Array(await crypto.subtle.exportKey("pkcs8", kp.privateKey) as ArrayBuffer);
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

describe("normKey", () => {
  it.each(vectors as [string, string][])("normalises %j", (input, want) => {
    expect(normKey(input)).toBe(want);
  });
  it("activates with a sloppy key", async () => {
    const db = new MemoryDb();
    const key = await create(db);
    const sloppy = " " + key.toLowerCase().replace(/-/g, "\u2013") + "\u200b";
    expect((await handle(post("/v1/activate", { key: sloppy, machine: "m1" }), env, db)).status).toBe(200);
  });
});

describe("activation race", () => {
  it("two machines activating the same unbound key at once: exactly one 200", async () => {
    const db = new MemoryDb();
    const key = await create(db);
    const rs = await Promise.all([
      handle(post("/v1/activate", { key, machine: "m1" }), env, db),
      handle(post("/v1/activate", { key, machine: "m2" }), env, db),
    ]);
    expect(rs.map((r) => r.status).sort()).toEqual([200, 409]);
    const winner = rs.findIndex((r) => r.status === 200) === 0 ? "m1" : "m2";
    expect((await db.get(key))!.machine).toBe(winner);
  });

  it("a revoke between the read and the update yields 410 and no token", async () => {
    class RevokingDb extends MemoryDb {
      armed = false;
      async get(key: string) { const r = await super.get(key); if (this.armed) { this.armed = false; this.rows.get(key)!.status = "revoked"; } return r; }
    }
    const db = new RevokingDb();
    const key = await create(db);
    db.armed = true;
    const r = await handle(post("/v1/activate", { key, machine: "m1" }), env, db);
    expect(r.status).toBe(410);
    expect(await r.json()).toEqual({ error: "revoked" });
    expect((await db.get(key))!.machine).toBeNull();
  });

  it("re-activation on the bound machine keeps activated_at", async () => {
    const db = new MemoryDb();
    const key = await create(db);
    await handle(post("/v1/activate", { key, machine: "m1" }), env, db, () => new Date("2026-01-01T00:00:00Z"));
    await handle(post("/v1/activate", { key, machine: "m1" }), env, db, () => new Date("2026-02-01T00:00:00Z"));
    const row = (await db.get(key))!;
    expect(row.activated_at).toBe("2026-01-01T00:00:00.000Z");
    expect(row.last_seen_at).toBe("2026-02-01T00:00:00.000Z");
  });
});

describe("cross-implementation vector", () => {
  it("the committed fixture is exactly what signLicense produces (Ed25519 is deterministic)", async () => {
    // @ts-expect-error plain .mjs helper, no types
    const { makeVector } = await import("../scripts/gen-vector.mjs");
    const fixture = (await import("../../app/src-tauri/tests/fixtures/license-vector.json")).default;
    expect(await makeVector()).toEqual(fixture);
  });
});
