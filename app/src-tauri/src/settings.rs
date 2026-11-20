use serde::{Deserialize, Serialize};
use std::path::Path;

use crate::paths::default_projects_root;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct Settings {
    pub model: String,
    pub projects_root: String,
    pub last_niche: Option<String>,
    pub onboarded: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            model: "claude-opus-5-5".into(),
            projects_root: default_projects_root().to_string_lossy().into_owned(),
            last_niche: None,
            onboarded: false,
        }
    }
}

pub fn load(dir: &Path) -> Settings {
    std::fs::read_to_string(dir.join("settings.json"))
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_default()
}

pub fn save(dir: &Path, s: &Settings) -> std::io::Result<()> {
    std::fs::create_dir_all(dir)?;
    let tmp = dir.join("settings.json.tmp");
    std::fs::write(&tmp, serde_json::to_string_pretty(s).map_err(std::io::Error::other)?)?;
    std::fs::rename(&tmp, dir.join("settings.json"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn load_missing_gives_default() {
        let d = tempfile::tempdir().unwrap();
        let s = load(d.path());
        assert_eq!(s.model, "claude-opus-5-5");
        assert!(!s.onboarded);
    }
    #[test]
    fn save_then_load_roundtrip_camel_case() {
        let d = tempfile::tempdir().unwrap();
        let s = Settings { onboarded: true, last_niche: Some("my-pham".into()), ..Default::default() };
        save(d.path(), &s).unwrap();
        let raw = std::fs::read_to_string(d.path().join("settings.json")).unwrap();
        assert!(raw.contains("\"lastNiche\""));
        assert_eq!(load(d.path()), s);
    }
    #[test]
    fn corrupt_file_gives_default() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("settings.json"), "{oops").unwrap();
        assert_eq!(load(d.path()).model, "claude-opus-5-5");
    }
}
