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
        let o = std::process::Command::new("/usr/sbin/ioreg")
            .args(["-rd1", "-c", "IOPlatformExpertDevice"])
            .output()
            .map_err(|e| e.to_string())?;
        parse_ioreg(&String::from_utf8_lossy(&o.stdout))
    };
    #[cfg(target_os = "windows")]
    let id = {
        use std::os::windows::process::CommandExt;
        let o = std::process::Command::new("reg")
            .args(["query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"])
            .creation_flags(0x0800_0000) // CREATE_NO_WINDOW
            .output()
            .map_err(|e| e.to_string())?;
        parse_reg(&String::from_utf8_lossy(&o.stdout))
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

/// Commands that work while the app is locked.
pub const OPEN_COMMANDS: &[&str] = &["license_status", "license_activate", "kill_all_jobs"];

/// Plugin commands that do something for the user (files, links, relaunch, updates) are gated like
/// app commands. The rest (event listen/emit, window and webview plumbing) must keep working so
/// the activation screen can load and hear `license-revoked`.
const GATED_PLUGINS: &[&str] = &["plugin:dialog|", "plugin:opener|", "plugin:process|", "plugin:updater|"];

pub fn allowed(cmd: &str, licensed: bool) -> bool {
    if licensed || OPEN_COMMANDS.contains(&cmd) {
        return true;
    }
    cmd.starts_with("plugin:") && !GATED_PLUGINS.iter().any(|p| cmd.starts_with(p))
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
        assert!(allowed("kill_all_jobs", false));
        assert!(!allowed("engine_run", false));
        assert!(!allowed("create_project", false));
        assert!(allowed("engine_run", true));
    }

    #[test]
    fn plugin_commands_that_touch_the_user_are_gated_but_event_plumbing_is_not() {
        assert!(allowed("plugin:event|listen", false)); // the activation screen listens for license-revoked
        assert!(!allowed("plugin:dialog|open", false));
        assert!(!allowed("plugin:opener|open_url", false));
        assert!(!allowed("plugin:process|restart", false));
        assert!(!allowed("plugin:updater|check", false));
        assert!(allowed("plugin:dialog|open", true));
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
        for c in OPEN_COMMANDS {
            assert!(cmds.contains(c), "{c} is open but not a registered command");
        }
        for c in &cmds {
            assert_eq!(allowed(c, false), OPEN_COMMANDS.contains(c), "{c}");
        }
    }
}
