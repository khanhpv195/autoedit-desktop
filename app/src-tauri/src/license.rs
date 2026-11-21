//! License gate: machine hash, offline token verification, activation API calls (spec 2026-11-21).
use base64::Engine;
use base64::engine::general_purpose::{STANDARD, URL_SAFE_NO_PAD as B64URL};
use ed25519_dalek::{Signature, VerifyingKey};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use crate::secrets::{SecretStore, LICENSE_ACCOUNT};

pub const URL: &str = env!("AUTOEDIT_LICENSE_URL");
pub const PUBKEY: &str = env!("AUTOEDIT_LICENSE_PUBKEY");
const USER_AGENT: &str = concat!("AutoEdit/", env!("CARGO_PKG_VERSION"));

#[derive(Debug, Clone, Deserialize)]
pub struct License {
    pub key: String,
    pub machine: String,
    pub name: String,
    #[allow(dead_code)] // part of the signed payload, not used by the app
    pub iat: i64,
}

pub fn verify_token(token: &str, pubkey_b64: &str, machine: &str) -> Result<License, String> {
    let (payload, sig) = token.trim().split_once('.').ok_or("malformed")?;
    let pk: [u8; 32] = STANDARD
        .decode(pubkey_b64)
        .map_err(|_| "bad pubkey")?
        .try_into()
        .map_err(|_| "bad pubkey")?;
    let vk = VerifyingKey::from_bytes(&pk).map_err(|_| "bad pubkey")?;
    let sig = Signature::from_slice(&B64URL.decode(sig).map_err(|_| "malformed")?).map_err(|_| "malformed")?;
    vk.verify_strict(payload.as_bytes(), &sig).map_err(|_| "bad signature")?;
    let l: License =
        serde_json::from_slice(&B64URL.decode(payload).map_err(|_| "malformed")?).map_err(|_| "malformed")?;
    if l.machine != machine {
        return Err("other machine".into());
    }
    Ok(l)
}

pub fn hash_platform_id(id: &str) -> String {
    let d = Sha256::digest(format!("autoedit:{}", id.trim()).as_bytes());
    d.iter().take(16).map(|b| format!("{b:02x}")).collect()
}

#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
fn parse_ioreg(out: &str) -> Option<String> {
    let line = out.lines().find(|l| l.contains("\"IOPlatformUUID\""))?;
    let v = line.split('=').nth(1)?.trim().trim_matches('"');
    (!v.is_empty()).then(|| v.to_string())
}

pub fn machine_hash() -> Result<String, String> {
    #[cfg(target_os = "macos")]
    let id = {
        let o = std::process::Command::new("/usr/sbin/ioreg")
            .args(["-rd1", "-c", "IOPlatformExpertDevice"])
            .output()
            .map_err(|e| e.to_string())?;
        parse_ioreg(&String::from_utf8_lossy(&o.stdout))
    };
    #[cfg(target_os = "windows")]
    let id = {
        // Registry API, not `reg.exe`: no child process, nothing to hijack through PATH.
        use winreg::RegKey;
        use winreg::enums::{HKEY_LOCAL_MACHINE, KEY_READ, KEY_WOW64_64KEY};
        RegKey::predef(HKEY_LOCAL_MACHINE)
            .open_subkey_with_flags(r"SOFTWARE\Microsoft\Cryptography", KEY_READ | KEY_WOW64_64KEY)
            .and_then(|k| k.get_value::<String, _>("MachineGuid"))
            .ok()
            .filter(|g| !g.trim().is_empty())
    };
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    let id = std::fs::read_to_string("/etc/machine-id").ok();
    id.map(|i| hash_platform_id(&i)).ok_or_else(|| "Không đọc được mã máy".into())
}

#[derive(Debug)]
pub enum Remote {
    Ok(String),
    Invalid,
    Used,
    Revoked,
    Offline,
}

pub fn code(r: &Remote) -> &'static str {
    match r {
        Remote::Invalid => "LICENSE_INVALID",
        Remote::Used => "LICENSE_USED",
        Remote::Revoked => "LICENSE_REVOKED",
        Remote::Offline | Remote::Ok(_) => "LICENSE_OFFLINE",
    }
}

/// Only a JSON body from our Worker with the exact `error` code is a verdict. Anything else
/// (an HTML 404 from a proxy, a wrong path answering `not_found`, a captive portal) is Offline:
/// it must never lock a paying customer out. `field` is the success field for a 200
/// (`license` for activation, `status` for a check).
fn from_status(status: u16, body: &str, field: &str) -> Remote {
    let v: serde_json::Value = match serde_json::from_str(body) {
        Ok(v) => v,
        Err(_) => return Remote::Offline,
    };
    match (status, v["error"].as_str()) {
        (200, _) => match v[field].as_str() {
            Some(s) if !s.is_empty() && (field != "status" || s == "active") => Remote::Ok(s.to_string()),
            _ => Remote::Offline,
        },
        (404, Some("invalid")) => Remote::Invalid,
        (409, Some("used_elsewhere")) => Remote::Used,
        (410, Some("revoked")) => Remote::Revoked,
        _ => Remote::Offline,
    }
}

async fn post(url: &str, path: &str, field: &str, body: serde_json::Value) -> Remote {
    if url.is_empty() {
        return Remote::Offline;
    }
    let client = match reqwest::Client::builder()
        .user_agent(USER_AGENT)
        .timeout(std::time::Duration::from_secs(15))
        .build()
    {
        Ok(c) => c,
        Err(_) => return Remote::Offline,
    };
    match client.post(format!("{url}{path}")).json(&body).send().await {
        Ok(r) => {
            let s = r.status().as_u16();
            from_status(s, &r.text().await.unwrap_or_default(), field)
        }
        Err(_) => Remote::Offline,
    }
}

pub async fn activate(url: &str, key: &str, machine: &str, version: &str) -> Remote {
    post(url, "/v1/activate", "license", serde_json::json!({"key": key.trim(), "machine": machine, "app_version": version})).await
}

pub async fn check(url: &str, key: &str, machine: &str) -> Remote {
    post(url, "/v1/check", "status", serde_json::json!({"key": key, "machine": machine})).await
}

/// Commands that work while the app is locked.
pub const OPEN_COMMANDS: &[&str] = &["license_status", "license_activate", "kill_all_jobs"];

/// App commands (everything in `generate_handler!`) are refused until licensed, except OPEN_COMMANDS.
/// Plugin commands (`plugin:*|*`: dialog, opener, process, updater, event) are routed by Tauri to
/// the plugin handlers and never reach the app's invoke handler, so they are NOT gated here. They
/// cannot unlock editing: every action that produces or changes a project goes through an app command.
pub fn allowed(cmd: &str, licensed: bool) -> bool {
    licensed || OPEN_COMMANDS.contains(&cmd)
}

#[derive(Debug, PartialEq, Eq)]
pub enum SetError {
    /// The token the server issued does not verify against the bundled public key / this machine.
    Verify,
    /// Keychain write failed.
    Store,
}

/// Background-check bookkeeping, kept pure so it can be tested without a clock or a network.
pub const CHECK_EVERY: std::time::Duration = std::time::Duration::from_secs(6 * 3600);
pub const POLL_EVERY: std::time::Duration = std::time::Duration::from_secs(15 * 60);
pub const INVALID_CONFIRM_GAP: std::time::Duration = std::time::Duration::from_secs(3600);

/// Wall-clock based so a laptop that slept for a day checks right after waking. A clock that
/// moved backwards counts as due.
pub fn check_due(last: Option<std::time::SystemTime>, now: std::time::SystemTime) -> bool {
    match last {
        None => true,
        Some(t) => now.duration_since(t).map_or(true, |d| d >= CHECK_EVERY),
    }
}

#[derive(Default)]
pub struct Verdicts {
    first_invalid: Option<std::time::SystemTime>,
}

impl Verdicts {
    /// Some(code) = lock the app (and delete the token) with this reason.
    /// Revoked/Used lock at once. Invalid locks only on a second definitive `invalid` at least
    /// INVALID_CONFIRM_GAP after the first. Offline changes nothing; a good answer resets.
    pub fn apply(&mut self, r: &Remote, now: std::time::SystemTime) -> Option<&'static str> {
        match r {
            Remote::Revoked | Remote::Used => {
                self.first_invalid = None;
                Some(code(r))
            }
            Remote::Invalid => match self.first_invalid {
                Some(t) if now.duration_since(t).is_ok_and(|d| d >= INVALID_CONFIRM_GAP) => {
                    self.first_invalid = None;
                    Some(code(r))
                }
                Some(_) => None,
                None => {
                    self.first_invalid = Some(now);
                    None
                }
            },
            Remote::Ok(_) => {
                self.first_invalid = None;
                None
            }
            Remote::Offline => None,
        }
    }
}

pub struct Gate {
    licensed: AtomicBool,
    license: Mutex<Option<License>>,
    machine: String,
}

impl Gate {
    pub fn load(store: &dyn SecretStore, pubkey: &str) -> Gate {
        Self::load_for(store, pubkey, machine_hash().unwrap_or_default())
    }

    pub fn load_for(store: &dyn SecretStore, pubkey: &str, machine: String) -> Gate {
        let lic = store.get(LICENSE_ACCOUNT).and_then(|t| verify_token(&t, pubkey, &machine).ok());
        let dev = cfg!(debug_assertions) && std::env::var("AUTOEDIT_LICENSE_DEV").as_deref() == Ok("1");
        Gate { licensed: AtomicBool::new(lic.is_some() || dev), license: Mutex::new(lic), machine }
    }

    pub fn is_licensed(&self) -> bool {
        self.licensed.load(Ordering::SeqCst)
    }
    pub fn machine(&self) -> &str {
        &self.machine
    }
    pub fn key(&self) -> Option<String> {
        self.license.lock().unwrap().as_ref().map(|l| l.key.clone())
    }
    pub fn name(&self) -> Option<String> {
        self.license.lock().unwrap().as_ref().map(|l| l.name.clone())
    }

    pub fn set(&self, store: &dyn SecretStore, token: &str, pubkey: &str) -> Result<License, SetError> {
        let l = verify_token(token, pubkey, &self.machine).map_err(|_| SetError::Verify)?;
        store.set(LICENSE_ACCOUNT, token).map_err(|_| SetError::Store)?;
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

#[cfg(test)]
mod tests {
    use super::*;
    use base64::Engine;
    use base64::engine::general_purpose::{STANDARD, URL_SAFE_NO_PAD as B64URL};
    use ed25519_dalek::{Signer, SigningKey};

    fn keypair() -> (SigningKey, String) {
        let sk = SigningKey::from_bytes(&[7u8; 32]);
        let pk = STANDARD.encode(sk.verifying_key().to_bytes());
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
    fn parses_ioreg_output() {
        let ioreg = "  |   \"IOPlatformUUID\" = \"1234ABCD-0000-1111-2222-333344445555\"\n";
        assert_eq!(parse_ioreg(ioreg).as_deref(), Some("1234ABCD-0000-1111-2222-333344445555"));
        assert_eq!(parse_ioreg("nothing"), None);
    }

    #[test]
    fn this_machine_has_a_hash() {
        assert_eq!(machine_hash().unwrap().len(), 32);
    }

    const NOT_FOUND: &str = r#"{"error":"not_found"}"#;

    #[test]
    fn only_exact_json_error_codes_are_verdicts() {
        let act = |st, b| from_status(st, b, "license");
        assert!(matches!(act(404, r#"{"error":"invalid"}"#), Remote::Invalid));
        assert!(matches!(act(409, r#"{"error":"used_elsewhere"}"#), Remote::Used));
        assert!(matches!(act(410, r#"{"error":"revoked"}"#), Remote::Revoked));
        // wrong path on the Worker, HTML from a proxy, empty bodies, mismatched code/status: never a lock-out
        assert!(matches!(act(404, NOT_FOUND), Remote::Offline));
        assert!(matches!(act(404, "<html>Not Found</html>"), Remote::Offline));
        assert!(matches!(act(404, ""), Remote::Offline));
        assert!(matches!(act(410, "<html>Gone</html>"), Remote::Offline));
        assert!(matches!(act(409, r#"{"error":"revoked"}"#), Remote::Offline));
        assert!(matches!(act(410, r#"{"error":"invalid"}"#), Remote::Offline));
        assert!(matches!(act(500, r#"{"error":"invalid"}"#), Remote::Offline));
        assert!(matches!(act(503, r#"{"error":"retry"}"#), Remote::Offline));
        assert_eq!(code(&Remote::Used), "LICENSE_USED");
    }

    #[test]
    fn ok_bodies_need_the_expected_field() {
        assert!(matches!(from_status(200, r#"{"license":"t.s"}"#, "license"), Remote::Ok(ref t) if t == "t.s"));
        assert!(matches!(from_status(200, r#"{"status":"active"}"#, "status"), Remote::Ok(ref s) if s == "active"));
        assert!(matches!(from_status(200, "<html>captive portal</html>", "license"), Remote::Offline));
        assert!(matches!(from_status(200, "{}", "license"), Remote::Offline));
        assert!(matches!(from_status(200, r#"{"status":"active"}"#, "license"), Remote::Offline));
        assert!(matches!(from_status(200, r#"{"license":"t.s"}"#, "status"), Remote::Offline));
        assert!(matches!(from_status(200, r#"{"status":"weird"}"#, "status"), Remote::Offline));
    }

    #[test]
    fn revoked_and_used_lock_at_once_invalid_needs_two_checks_an_hour_apart() {
        use std::time::{Duration, SystemTime};
        let t0 = SystemTime::UNIX_EPOCH + Duration::from_secs(1_800_000_000);
        let h = Duration::from_secs(3600);
        let mut v = Verdicts::default();
        assert_eq!(v.apply(&Remote::Revoked, t0), Some("LICENSE_REVOKED"));
        assert_eq!(v.apply(&Remote::Used, t0), Some("LICENSE_USED"));
        assert_eq!(v.apply(&Remote::Offline, t0), None);

        assert_eq!(v.apply(&Remote::Invalid, t0), None); // first: keep
        assert_eq!(v.apply(&Remote::Invalid, t0 + h / 2), None); // too soon: still keep
        assert_eq!(v.apply(&Remote::Offline, t0 + h), None); // offline neither counts nor resets
        assert_eq!(v.apply(&Remote::Invalid, t0 + h), Some("LICENSE_INVALID"));

        let mut v = Verdicts::default();
        assert_eq!(v.apply(&Remote::Invalid, t0), None);
        assert_eq!(v.apply(&Remote::Ok("active".into()), t0 + h), None); // a good answer resets
        assert_eq!(v.apply(&Remote::Invalid, t0 + 2 * h), None);
    }

    #[test]
    fn check_is_due_by_wall_clock() {
        use std::time::{Duration, SystemTime};
        let t0 = SystemTime::UNIX_EPOCH + Duration::from_secs(1_800_000_000);
        let h = Duration::from_secs(3600);
        assert!(check_due(None, t0));
        assert!(!check_due(Some(t0), t0 + 5 * h));
        assert!(check_due(Some(t0), t0 + 6 * h));
        assert!(check_due(Some(t0), t0 + 30 * h)); // woke from a long sleep
        assert!(check_due(Some(t0 + h), t0)); // clock went backwards
    }

    #[tokio::test]
    async fn unreachable_server_is_offline() {
        assert!(matches!(activate("http://127.0.0.1:9", "AE-X", "m1", "0").await, Remote::Offline));
    }

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
        assert!(gate_with(&store, &pk, "m1").is_licensed()); // next launch, offline
        assert!(!gate_with(&store, &pk, "m2").is_licensed()); // copied Keychain to another machine
    }

    #[test]
    fn gate_set_distinguishes_verify_failure_from_keychain_failure() {
        struct FailingStore;
        impl SecretStore for FailingStore {
            fn get(&self, _: &str) -> Option<String> { None }
            fn set(&self, _: &str, _: &str) -> Result<(), String> { Err("denied".into()) }
            fn delete(&self, _: &str) -> Result<(), String> { Ok(()) }
        }
        let (sk, pk) = keypair();
        let g = Gate::load_for(&FailingStore, &pk, "m1".into());
        assert_eq!(g.set(&FailingStore, &token(&sk, PAYLOAD), &pk).unwrap_err(), SetError::Store);
        assert!(!g.is_licensed());
        assert_eq!(g.set(&FailingStore, "garbage", &pk).unwrap_err(), SetError::Verify);
        assert_eq!(g.set(&FailingStore, &token(&sk, PAYLOAD), "").unwrap_err(), SetError::Verify);
    }

    #[test]
    fn gate_set_rejects_token_for_other_machine_and_revoke_clears() {
        let (sk, pk) = keypair();
        let store = MemoryStore::default();
        let g = gate_with(&store, &pk, "m2");
        assert_eq!(g.set(&store, &token(&sk, PAYLOAD), &pk).unwrap_err(), SetError::Verify);
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
        assert!(allowed("kill_all_jobs", false));
        assert!(!allowed("engine_run", false));
        assert!(!allowed("create_project", false));
        assert!(allowed("engine_run", true));
        for c in ["eleven_status", "set_eleven_key", "clear_eleven_key", "eleven_voices"] {
            assert!(!allowed(c, false) && allowed(c, true), "{c}");
        }
    }

    /// Fixture produced by license-server/scripts/gen-vector.mjs with the Worker's own signLicense().
    #[test]
    fn token_signed_by_the_worker_verifies_here() {
        let v: serde_json::Value = serde_json::from_str(include_str!("../tests/fixtures/license-vector.json")).unwrap();
        let (pk, token, machine) = (v["pubkey"].as_str().unwrap(), v["token"].as_str().unwrap(), v["machine"].as_str().unwrap());
        let l = verify_token(token, pk, machine).unwrap();
        assert_eq!(l.key, v["key"].as_str().unwrap());
        assert_eq!(l.name, v["name"].as_str().unwrap());
        assert!(verify_token(token, pk, "other-machine").is_err());
        let mut bad = token.to_string();
        bad.replace_range(5..6, if &bad[5..6] == "A" { "B" } else { "A" });
        assert!(verify_token(&bad, pk, machine).is_err());
    }

    /// Every command in generate_handler! goes through the central gate in lib.rs; the only
    /// way past it while unlicensed is OPEN_COMMANDS. Guards typos there and a command that
    /// someone adds to the open list without it existing.
    #[test]
    fn every_registered_command_is_gated_except_the_open_ones() {
        let lib = include_str!("lib.rs");
        let list = lib.split("generate_handler![").nth(1).unwrap().split(']').next().unwrap();
        let cmds: Vec<&str> = list.split(',').filter_map(|c| c.trim().strip_prefix("commands::")).collect();
        assert!(cmds.len() > 20, "failed to parse the command list");
        for c in ["eleven_status", "set_eleven_key", "clear_eleven_key", "eleven_voices"] {
            assert!(cmds.contains(&c), "{c} is not registered");
        }
        for c in OPEN_COMMANDS {
            assert!(cmds.contains(c), "{c} is open but not a registered command");
        }
        for c in &cmds {
            assert_eq!(allowed(c, false), OPEN_COMMANDS.contains(c), "{c}");
        }
    }
}
