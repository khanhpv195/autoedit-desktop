// Regenerates app/src-tauri/tests/fixtures/license-vector.json: a token signed by the Worker's own
// signLicense() with a fixed, PUBLIC, test-only key (seed = 32 x 0x2a, never used anywhere real).
// The Rust test verifies it with verify_token, so the two implementations cannot drift apart.
// Run: node scripts/gen-vector.mjs   (Node 22.6+ strips the TypeScript types on import)
import { writeFileSync } from "node:fs";
import { signLicense } from "../src/core.ts";

export const SEED = new Uint8Array(32).fill(0x2a);
export const MACHINE = "0123456789abcdef0123456789abcdef";
export const ROW = { key: "AE-7KQ2-M9XD-0011-ZZZZ", name: "Cross Test" };
export const IAT = new Date("2026-11-21T00:00:00Z");

const PKCS8_PREFIX = Buffer.from("302e020100300506032b657004220420", "hex");
export const signingKeyB64 = Buffer.concat([PKCS8_PREFIX, SEED]).toString("base64");

export async function makeVector() {
  const priv = await crypto.subtle.importKey("pkcs8", Buffer.from(signingKeyB64, "base64"), { name: "Ed25519" }, true, ["sign"]);
  const jwk = await crypto.subtle.exportKey("jwk", priv);
  const pubkey = Buffer.from(jwk.x, "base64url").toString("base64");
  const token = await signLicense({ ADMIN_TOKEN: "", LICENSE_SIGNING_KEY: signingKeyB64 }, ROW, MACHINE, IAT);
  return { pubkey, token, machine: MACHINE, key: ROW.key, name: ROW.name };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const out = new URL("../../app/src-tauri/tests/fixtures/license-vector.json", import.meta.url);
  writeFileSync(out, JSON.stringify(await makeVector(), null, 2) + "\n");
  console.log("wrote", out.pathname);
}
