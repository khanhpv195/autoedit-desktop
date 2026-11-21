
pub const OAUTH_ACCOUNT: &str = "claude-oauth-token";
pub const SOCIAL_ACCOUNT: &str = "bundle-social-key";
pub const API_KEY_ACCOUNT: &str = "anthropic-api-key";
pub const LICENSE_ACCOUNT: &str = "license";
const SERVICE: &str = "AutoEdit";

pub trait SecretStore {
    fn get(&self, account: &str) -> Option<String>;
    fn set(&self, account: &str, value: &str) -> Result<(), String>;
    fn delete(&self, account: &str) -> Result<(), String>;
}

/// OS credential store (macOS Keychain / Windows Credential Manager).
pub struct KeyringStore;

impl KeyringStore {
    fn entry(account: &str) -> Result<keyring::Entry, String> {
        keyring::Entry::new(SERVICE, account).map_err(|e| e.to_string())
    }
}

impl SecretStore for KeyringStore {
    fn get(&self, account: &str) -> Option<String> {
        Self::entry(account).ok()?.get_password().ok()
    }
    fn set(&self, account: &str, value: &str) -> Result<(), String> {
        Self::entry(account)?.set_password(value).map_err(|e| e.to_string())
    }
    fn delete(&self, account: &str) -> Result<(), String> {
        match Self::entry(account)?.delete_credential() {
            Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
            Err(e) => Err(e.to_string()),
        }
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
}
