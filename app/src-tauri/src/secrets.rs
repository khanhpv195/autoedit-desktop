
pub const OAUTH_ACCOUNT: &str = "claude-oauth-token";
pub const SOCIAL_ACCOUNT: &str = "bundle-social-key";
pub const API_KEY_ACCOUNT: &str = "anthropic-api-key";
pub const LICENSE_ACCOUNT: &str = "license";
pub const ELEVEN_ACCOUNT: &str = "elevenlabs";
const SERVICE: &str = "AutoEdit";

pub trait SecretStore {
    fn get(&self, account: &str) -> Option<String>;
    fn set(&self, account: &str, value: &str) -> Result<(), String>;
    fn delete(&self, account: &str) -> Result<(), String>;
}

/// Raw OS credential store: one keyring item per account. `Ok(None)` = no such item; `Err` = the store refused
/// (locked, or the user pressed Deny).
pub trait RawStore {
    fn read(&self, account: &str) -> Result<Option<String>, String>;
    fn write(&self, account: &str, value: &str) -> Result<(), String>;
    fn remove(&self, account: &str) -> Result<(), String>;
}

pub struct Keyring;

impl Keyring {
    fn entry(account: &str) -> Result<keyring::Entry, String> {
        keyring::Entry::new(SERVICE, account).map_err(|e| e.to_string())
    }
}

impl RawStore for Keyring {
    fn read(&self, account: &str) -> Result<Option<String>, String> {
        match Self::entry(account)?.get_password() {
            Ok(v) => Ok(Some(v)),
            Err(keyring::Error::NoEntry) => Ok(None),
            Err(e) => Err(e.to_string()),
        }
    }
    fn write(&self, account: &str, value: &str) -> Result<(), String> {
        Self::entry(account)?.set_password(value).map_err(|e| e.to_string())
    }
    fn remove(&self, account: &str) -> Result<(), String> {
        match Self::entry(account)?.delete_credential() {
            Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
            Err(e) => Err(e.to_string()),
        }
    }
}

/// Every secret in ONE keyring item (a JSON map), read once per run. macOS asks for the login password per item
/// whenever the app's signature changes (every update of an ad-hoc signed build), so one item = one prompt.
/// Items of older versions (one per account) are moved in the first time each account is asked for.
const BUNDLE_ACCOUNT: &str = "secrets";

type Map = std::collections::BTreeMap<String, String>;

#[derive(Default)]
struct State {
    map: Map,
    no_legacy: std::collections::HashSet<String>,   // accounts already looked up in the old per-account items
}

pub struct BundleStore<R: RawStore> {
    raw: R,
    state: std::sync::Mutex<Option<State>>,     // None until the bundle was read successfully
}

impl<R: RawStore> BundleStore<R> {
    pub const fn new(raw: R) -> Self {
        Self { raw, state: std::sync::Mutex::new(None) }
    }

    /// Runs `f` on the loaded state. A refused read is not cached and gives Err, so a later write never
    /// overwrites secrets it could not see.
    fn with_state<T>(&self, f: impl FnOnce(&mut State) -> Result<T, String>) -> Result<T, String> {
        let mut guard = self.state.lock().map_err(|_| "secret store poisoned".to_string())?;
        if guard.is_none() {
            let map = match self.raw.read(BUNDLE_ACCOUNT)? {
                Some(json) => serde_json::from_str(&json).map_err(|e| format!("secret bundle unreadable: {e}"))?,
                None => Map::new(),
            };
            *guard = Some(State { map, ..Default::default() });
        }
        f(guard.as_mut().expect("loaded"))
    }

    /// Moves `account`'s old per-account item (if any) into the bundle; once per account per run.
    fn adopt_legacy(&self, st: &mut State, account: &str) -> Result<(), String> {
        if st.map.contains_key(account) || st.no_legacy.contains(account) {
            return Ok(());
        }
        if let Some(v) = self.raw.read(account)? {
            let mut next = st.map.clone();
            next.insert(account.to_string(), v);
            self.save(&next)?;
            st.map = next;
            let _ = self.raw.remove(account);
        }
        st.no_legacy.insert(account.to_string());
        Ok(())
    }

    fn save(&self, map: &Map) -> Result<(), String> {
        if map.is_empty() {
            return self.raw.remove(BUNDLE_ACCOUNT);
        }
        self.raw.write(BUNDLE_ACCOUNT, &serde_json::to_string(map).map_err(|e| e.to_string())?)
    }

    fn put(&self, account: &str, value: Option<&str>) -> Result<(), String> {
        self.with_state(|st| {
            self.adopt_legacy(st, account)?;
            let mut next = st.map.clone();
            match value {
                Some(v) => next.insert(account.to_string(), v.to_string()),
                None if !next.contains_key(account) => return Ok(()),
                None => next.remove(account),
            };
            self.save(&next)?;
            st.map = next;
            Ok(())
        })
    }
}

impl<R: RawStore> SecretStore for BundleStore<R> {
    fn get(&self, account: &str) -> Option<String> {
        self.with_state(|st| {
            self.adopt_legacy(st, account)?;
            Ok(st.map.get(account).cloned())
        })
        .ok()
        .flatten()
    }
    fn set(&self, account: &str, value: &str) -> Result<(), String> {
        self.put(account, Some(value))
    }
    fn delete(&self, account: &str) -> Result<(), String> {
        self.put(account, None)
    }
}

/// OS credential store (macOS Keychain / Windows Credential Manager). On macOS all secrets share one Keychain
/// item (one password prompt after an update, not one per secret); on Windows, one item per secret (no prompts
/// there, and Credential Manager caps an item at ~2.5 KB).
pub struct KeyringStore;

#[cfg(target_os = "macos")]
static BUNDLE: BundleStore<Keyring> = BundleStore::new(Keyring);

impl SecretStore for KeyringStore {
    fn get(&self, account: &str) -> Option<String> {
        #[cfg(target_os = "macos")]
        return BUNDLE.get(account);
        #[cfg(not(target_os = "macos"))]
        return Keyring.read(account).ok().flatten();
    }
    fn set(&self, account: &str, value: &str) -> Result<(), String> {
        #[cfg(target_os = "macos")]
        return BUNDLE.set(account, value);
        #[cfg(not(target_os = "macos"))]
        return Keyring.write(account, value);
    }
    fn delete(&self, account: &str) -> Result<(), String> {
        #[cfg(target_os = "macos")]
        return BUNDLE.delete(account);
        #[cfg(not(target_os = "macos"))]
        return Keyring.remove(account);
    }
}

/// In-memory store for tests; never touches the real Keychain.
#[cfg(test)]
#[derive(Default)]
pub struct MemoryStore(std::sync::Mutex<std::collections::HashMap<String, String>>);

#[cfg(test)]
impl SecretStore for MemoryStore {
    fn get(&self, account: &str) -> Option<String> {
        self.0.lock().unwrap().get(account).cloned()
    }
    fn set(&self, account: &str, value: &str) -> Result<(), String> {
        self.0.lock().unwrap().insert(account.into(), value.into());
        Ok(())
    }
    fn delete(&self, account: &str) -> Result<(), String> {
        self.0.lock().unwrap().remove(account);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn memory_store_set_get_delete() {
        let m = MemoryStore::default();
        assert_eq!(m.get(OAUTH_ACCOUNT), None);
        m.set(OAUTH_ACCOUNT, "t").unwrap();
        assert_eq!(m.get(OAUTH_ACCOUNT).as_deref(), Some("t"));
        m.delete(OAUTH_ACCOUNT).unwrap();
        assert_eq!(m.get(OAUTH_ACCOUNT), None);
    }

    /// Fake keyring: counts reads; `deny` makes every call fail like a refused Keychain prompt.
    #[derive(Default)]
    struct FakeRaw {
        items: std::sync::Mutex<std::collections::HashMap<String, String>>,
        reads: std::sync::atomic::AtomicUsize,
        deny: std::sync::atomic::AtomicBool,
    }

    impl FakeRaw {
        fn with(items: &[(&str, &str)]) -> Self {
            let f = Self::default();
            for (k, v) in items {
                f.items.lock().unwrap().insert(k.to_string(), v.to_string());
            }
            f
        }
        fn denied(&self) -> Result<(), String> {
            if self.deny.load(std::sync::atomic::Ordering::SeqCst) { Err("denied".into()) } else { Ok(()) }
        }
    }

    impl RawStore for &FakeRaw {
        fn read(&self, a: &str) -> Result<Option<String>, String> {
            self.denied()?;
            self.reads.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            Ok(self.items.lock().unwrap().get(a).cloned())
        }
        fn write(&self, a: &str, v: &str) -> Result<(), String> {
            self.denied()?;
            self.items.lock().unwrap().insert(a.into(), v.into());
            Ok(())
        }
        fn remove(&self, a: &str) -> Result<(), String> {
            self.denied()?;
            self.items.lock().unwrap().remove(a);
            Ok(())
        }
    }

    #[test]
    fn bundle_reads_the_keychain_once_and_keeps_all_secrets_in_one_item() {
        let raw = FakeRaw::default();
        let s = BundleStore::new(&raw);
        s.set(LICENSE_ACCOUNT, "lic").unwrap();
        s.set(ELEVEN_ACCOUNT, "el").unwrap();
        assert_eq!(s.get(LICENSE_ACCOUNT).as_deref(), Some("lic"));
        assert_eq!(s.get(SOCIAL_ACCOUNT), None);
        let keys: Vec<String> = raw.items.lock().unwrap().keys().cloned().collect();
        assert_eq!(keys, vec![BUNDLE_ACCOUNT.to_string()]);
        let reads = raw.reads.load(std::sync::atomic::Ordering::SeqCst);
        s.get(ELEVEN_ACCOUNT);
        assert_eq!(raw.reads.load(std::sync::atomic::Ordering::SeqCst), reads);   // served from memory
        s.delete(LICENSE_ACCOUNT).unwrap();
        s.delete(ELEVEN_ACCOUNT).unwrap();
        assert!(raw.items.lock().unwrap().is_empty());
        // a fresh run sees what the last one saved
        s.set(OAUTH_ACCOUNT, "tok").unwrap();
        assert_eq!(BundleStore::new(&raw).get(OAUTH_ACCOUNT).as_deref(), Some("tok"));
    }

    #[test]
    fn bundle_moves_the_old_per_secret_items_into_one() {
        let raw = FakeRaw::with(&[(LICENSE_ACCOUNT, "lic"), (SOCIAL_ACCOUNT, "soc"), ("mcp:x:KEY", "k")]);
        let s = BundleStore::new(&raw);
        assert_eq!(s.get(SOCIAL_ACCOUNT).as_deref(), Some("soc"));
        assert_eq!(s.get(LICENSE_ACCOUNT).as_deref(), Some("lic"));
        s.set("mcp:x:KEY", "k2").unwrap();        // a write also takes over the old item
        let items = raw.items.lock().unwrap().clone();
        assert_eq!(items.keys().cloned().collect::<Vec<_>>(), vec![BUNDLE_ACCOUNT.to_string()]);
        let again = BundleStore::new(&raw);
        assert_eq!(again.get(LICENSE_ACCOUNT).as_deref(), Some("lic"));
        assert_eq!(again.get("mcp:x:KEY").as_deref(), Some("k2"));
        // a missing account is looked up in the old items once, then served from memory
        let reads = raw.reads.load(std::sync::atomic::Ordering::SeqCst);
        again.get(ELEVEN_ACCOUNT);
        again.get(ELEVEN_ACCOUNT);
        assert_eq!(raw.reads.load(std::sync::atomic::Ordering::SeqCst), reads + 1);
    }

    #[test]
    fn a_denied_read_never_overwrites_the_saved_secrets() {
        let raw = FakeRaw::default();
        BundleStore::new(&raw).set(LICENSE_ACCOUNT, "lic").unwrap();
        raw.deny.store(true, std::sync::atomic::Ordering::SeqCst);
        let s = BundleStore::new(&raw);
        assert_eq!(s.get(LICENSE_ACCOUNT), None);
        assert!(s.set(ELEVEN_ACCOUNT, "el").is_err());
        raw.deny.store(false, std::sync::atomic::Ordering::SeqCst);
        assert_eq!(s.get(LICENSE_ACCOUNT).as_deref(), Some("lic"));     // retried, not cached as empty
        s.set(ELEVEN_ACCOUNT, "el").unwrap();
        assert_eq!(BundleStore::new(&raw).get(LICENSE_ACCOUNT).as_deref(), Some("lic"));
    }
}
