use serde::{Deserialize, Serialize};
use std::path::Path;

use crate::paths::default_projects_root;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Routine {
    pub id: String,
    pub time: String,
    pub channels: Vec<String>,
    pub enabled: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct Settings {
    pub model: String,
    pub projects_root: String,
    pub last_niche: Option<String>,
    pub onboarded: bool,
    pub social_team_id: Option<String>,
    pub routines: Vec<Routine>,
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            model: "claude-opus-5-5".into(),
            projects_root: default_projects_root().to_string_lossy().into_owned(),
            last_niche: None,
            onboarded: false,
            social_team_id: None,
            routines: Vec::new(),
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
    fn old_settings_without_social_fields_still_load() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(
            d.path().join("settings.json"),
            r#"{"model":"m","projectsRoot":"/x","lastNiche":null,"onboarded":true}"#,
        )
        .unwrap();
        let s = load(d.path());
        assert!(s.onboarded);
        assert_eq!(s.model, "m");
        assert!(s.routines.is_empty());
        assert_eq!(s.social_team_id, None);
    }
    #[test]
    fn routines_roundtrip() {
        let d = tempfile::tempdir().unwrap();
        let s = Settings {
            social_team_id: Some("t1".into()),
            routines: vec![Routine { id: "r".into(), time: "19:30".into(), channels: vec!["TIKTOK".into()], enabled: true }],
            ..Default::default()
        };
        save(d.path(), &s).unwrap();
        assert!(std::fs::read_to_string(d.path().join("settings.json")).unwrap().contains("socialTeamId"));
        assert_eq!(load(d.path()), s);
    }
    #[test]
    fn corrupt_file_gives_default() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("settings.json"), "{oops").unwrap();
        assert_eq!(load(d.path()).model, "claude-opus-5-5");
    }
}
