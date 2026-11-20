use std::path::{Path, PathBuf};

use crate::secrets::{SecretStore, API_KEY_ACCOUNT, OAUTH_ACCOUNT};

/// Is there an existing Claude Code login on this machine?
pub fn has_claude_code(home: &Path, keychain: impl Fn() -> bool) -> bool {
    let config_dir = std::env::var_os("CLAUDE_CONFIG_DIR").map(PathBuf::from);
    has_claude_code_in(home, config_dir.as_deref(), keychain)
}

fn has_claude_code_in(home: &Path, config_dir: Option<&Path>, keychain: impl Fn() -> bool) -> bool {
    let dir = config_dir.map(Path::to_path_buf).unwrap_or_else(|| home.join(".claude"));
    dir.join(".credentials.json").is_file() || keychain()
}

/// macOS only: does the Keychain hold a `Claude Code-credentials` item?
/// Never asks for the secret (no `-w`/`-g`), so no prompt and nothing to leak.
pub fn mac_keychain_has_claude() -> bool {
    if !cfg!(target_os = "macos") {
        return false;
    }
    let Ok(mut child) = std::process::Command::new("security")
        .args(["find-generic-password", "-s", "Claude Code-credentials"])
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
    else {
        return false;
    };
    let until = std::time::Instant::now() + std::time::Duration::from_secs(5);
    loop {
        match child.try_wait() {
            Ok(Some(status)) => return status.success(),
            Ok(None) if std::time::Instant::now() < until => std::thread::sleep(std::time::Duration::from_millis(50)),
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                return false;
            }
        }
    }
}

pub fn status(secrets: &dyn SecretStore, has_cc: bool) -> Option<&'static str> {
    if secrets.get(OAUTH_ACCOUNT).is_some() {
        Some("app-token")
    } else if has_cc {
        Some("claude-code")
    } else if secrets.get(API_KEY_ACCOUNT).is_some() {
        Some("api-key")
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::secrets::MemoryStore;

    #[test]
    fn status_order() {
        let m = MemoryStore::default();
        assert_eq!(status(&m, false), None);
        m.set(API_KEY_ACCOUNT, "k").unwrap();
        assert_eq!(status(&m, false), Some("api-key"));
        assert_eq!(status(&m, true), Some("claude-code"));
        m.set(OAUTH_ACCOUNT, "t").unwrap();
        assert_eq!(status(&m, true), Some("app-token"));
    }
    #[test]
    fn claude_code_file_detected() {
        let h = tempfile::tempdir().unwrap();
        assert!(!has_claude_code_in(h.path(), None, || false));
        assert!(has_claude_code_in(h.path(), None, || true));
        std::fs::create_dir_all(h.path().join(".claude")).unwrap();
        std::fs::write(h.path().join(".claude/.credentials.json"), "{}").unwrap();
        assert!(has_claude_code_in(h.path(), None, || false));
    }
    #[test]
    fn config_dir_override_is_used() {
        let h = tempfile::tempdir().unwrap();
        let c = tempfile::tempdir().unwrap();
        std::fs::write(c.path().join(".credentials.json"), "{}").unwrap();
        assert!(has_claude_code_in(h.path(), Some(c.path()), || false));
    }
}
