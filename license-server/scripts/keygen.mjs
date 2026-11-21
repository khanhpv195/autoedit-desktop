// Prints a new Ed25519 pair. Private key -> `wrangler secret put LICENSE_SIGNING_KEY`; public key -> app/src-tauri/license.json.
const kp = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const priv = Buffer.from(await crypto.subtle.exportKey("pkcs8", kp.privateKey)).toString("base64");
const pub = Buffer.from(await crypto.subtle.exportKey("raw", kp.publicKey)).toString("base64");
console.log("PRIVATE (secret, paste into wrangler, keep in your password manager):\n" + priv);
console.log("\nPUBLIC (goes into app/src-tauri/license.json \"pubkey\"):\n" + pub);
