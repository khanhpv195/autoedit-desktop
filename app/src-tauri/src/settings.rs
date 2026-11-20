use serde::{Deserialize, Serialize};
use std::path::Path;

use crate::paths::default_projects_root;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Routine {
    pub id: String,
    pub time: String,
    pub channels: Vec<String>,
    pub enabled: bool,
}

impl Default for Routine {
    fn default() -> Self {
        Routine { id: String::new(), time: "19:30".into(), channels: Vec::new(), enabled: true }
    }
}

/// A malformed routine entry is dropped instead of failing the whole settings file.
fn lenient_routines<'de, D: serde::Deserializer<'de>>(d: D) -> Result<Vec<Routine>, D::Error> {
    let raw = Vec::<serde_json::Value>::deserialize(d).unwrap_or_default();
    Ok(raw.into_iter().filter_map(|v| serde_json::from_value::<Routine>(v).ok()).filter(|r| !r.id.is_empty()).collect())
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct Settings {
    pub model: String,
    pub projects_root: String,
    pub last_niche: Option<String>,
    pub onboarded: bool,
    pub social_team_id: Option<String>,
    #[serde(deserialize_with = "lenient_routines")]
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
    fn malformed_routine_is_dropped_and_settings_survive() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(
            d.path().join("settings.json"),
            r#"{"model":"m","onboarded":true,"routines":[{"id":"a","time":"08:00","channels":["TIKTOK"],"enabled":true},{"id":"b","time":5},"junk",{"id":"c"}]}"#,
        )
        .unwrap();
        let s = load(d.path());
        assert!(s.onboarded);
        assert_eq!(s.model, "m");
        let ids: Vec<_> = s.routines.iter().map(|r| r.id.as_str()).collect();
        assert_eq!(ids, ["a", "c"]);
        assert!(s.routines[1].channels.is_empty());
    }
    #[test]
    fn corrupt_file_gives_default() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("settings.json"), "{oops").unwrap();
        assert_eq!(load(d.path()).model, "claude-opus-5-5");
    }
}
