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
    /// Default ElevenLabs voice (not secret; the key lives in the Keychain).
    pub voice_id: Option<String>,
    pub voice_name: Option<String>,
    /// Absolute path of the app's own copy of the default logo (`<data_dir>/defaults/logo.<ext>`).
    pub default_logo: Option<String>,
    pub default_cta: String,
}

pub const DEFAULT_MODEL: &str = "claude-sonnet-5-5";
pub const DEFAULT_CTA: &str = "BẤM GIỎ HÀNG 👇";

impl Default for Settings {
    fn default() -> Self {
        Settings {
            model: DEFAULT_MODEL.into(),
            projects_root: default_projects_root().to_string_lossy().into_owned(),
            last_niche: None,
            onboarded: false,
            social_team_id: None,
            routines: Vec::new(),
            voice_id: None,
            voice_name: None,
            default_logo: None,
            default_cta: DEFAULT_CTA.into(),
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

pub const LOGO_EXT: [&str; 3] = ["png", "jpg", "jpeg"];

fn remove_old_logos(defaults: &Path) {
    let Ok(rd) = std::fs::read_dir(defaults) else { return };
    for e in rd.flatten() {
        if e.path().file_stem().is_some_and(|s| s == "logo") {
            let _ = std::fs::remove_file(e.path());
        }
    }
}

/// Copy `src` to `<data_dir>/defaults/logo.<ext>` (so the default survives the original being moved),
/// drop any older `logo.*`, and store the copy's absolute path as `defaultLogo`.
pub fn set_default_logo(data_dir: &Path, src: &Path) -> Result<Settings, String> {
    let ext = src.extension().map(|e| e.to_string_lossy().to_lowercase()).unwrap_or_default();
    if !LOGO_EXT.contains(&ext.as_str()) {
        return Err("Logo phải là ảnh PNG hoặc JPG".into());
    }
    if !src.is_file() {
        return Err(format!("Không thấy file {}", src.display()));
    }
    let defaults = data_dir.join("defaults");
    std::fs::create_dir_all(&defaults).map_err(|e| e.to_string())?;
    let tmp = defaults.join(format!("logo-new.{ext}"));
    std::fs::copy(src, &tmp).map_err(|e| format!("Không chép được logo: {e}"))?;
    remove_old_logos(&defaults);
    let dst = defaults.join(format!("logo.{ext}"));
    std::fs::rename(&tmp, &dst).map_err(|e| e.to_string())?;
    let mut s = load(data_dir);
    s.default_logo = Some(dst.to_string_lossy().into_owned());
    save(data_dir, &s).map_err(|e| e.to_string())?;
    Ok(s)
}

pub fn clear_default_logo(data_dir: &Path) -> Result<Settings, String> {
    remove_old_logos(&data_dir.join("defaults"));
    let mut s = load(data_dir);
    s.default_logo = None;
    save(data_dir, &s).map_err(|e| e.to_string())?;
    Ok(s)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn load_missing_gives_default() {
        let d = tempfile::tempdir().unwrap();
        let s = load(d.path());
        assert_eq!(s.model, "claude-sonnet-5-5");
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
    fn set_default_logo_copies_and_replaces_the_old_one() {
        let data = tempfile::tempdir().unwrap();
        let src = tempfile::tempdir().unwrap();
        let jpg = src.path().join("Shop Logo.JPG");
        std::fs::write(&jpg, b"jpg").unwrap();
        let s = set_default_logo(data.path(), &jpg).unwrap();
        let first = data.path().join("defaults").join("logo.jpg");
        assert_eq!(s.default_logo.as_deref(), Some(first.to_string_lossy().as_ref()));
        assert_eq!(std::fs::read(&first).unwrap(), b"jpg");
        assert_eq!(load(data.path()).default_logo, s.default_logo);

        let png = src.path().join("new.png");
        std::fs::write(&png, b"png").unwrap();
        let s = set_default_logo(data.path(), &png).unwrap();
        let second = data.path().join("defaults").join("logo.png");
        assert_eq!(s.default_logo.as_deref(), Some(second.to_string_lossy().as_ref()));
        assert!(!first.exists(), "old logo.jpg must be removed");
        assert_eq!(std::fs::read(&second).unwrap(), b"png");
        // the original survives being moved away
        std::fs::remove_file(&png).unwrap();
        assert!(second.is_file());
    }
    #[test]
    fn set_default_logo_rejects_gif_and_missing_files() {
        let data = tempfile::tempdir().unwrap();
        let gif = data.path().join("a.gif");
        std::fs::write(&gif, b"gif").unwrap();
        assert!(set_default_logo(data.path(), &gif).is_err());
        assert!(set_default_logo(data.path(), &data.path().join("nope.png")).is_err());
        assert_eq!(load(data.path()).default_logo, None);
    }
    #[test]
    fn clear_default_logo_removes_file_and_setting() {
        let data = tempfile::tempdir().unwrap();
        let png = data.path().join("x.png");
        std::fs::write(&png, b"png").unwrap();
        set_default_logo(data.path(), &png).unwrap();
        let s = clear_default_logo(data.path()).unwrap();
        assert_eq!(s.default_logo, None);
        assert_eq!(load(data.path()).default_logo, None);
        assert!(!data.path().join("defaults").join("logo.png").exists());
    }
    #[test]
    fn corrupt_file_gives_default() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("settings.json"), "{oops").unwrap();
        assert_eq!(load(d.path()).model, "claude-sonnet-5-5");
    }
    #[test]
    fn empty_json_gives_sonnet_and_new_defaults() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("settings.json"), "{}").unwrap();
        let s = load(d.path());
        assert_eq!(s.model, "claude-sonnet-5-5");
        assert_eq!(s.voice_id, None);
        assert_eq!(s.voice_name, None);
        assert_eq!(s.default_logo, None);
        assert_eq!(s.default_cta, "BẤM GIỎ HÀNG 👇");
    }
    #[test]
    fn old_settings_keep_saved_model_and_get_new_defaults() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(
            d.path().join("settings.json"),
            r#"{"model":"claude-opus-5-5","projectsRoot":"/x","lastNiche":null,"onboarded":true,"routines":[]}"#,
        )
        .unwrap();
        let s = load(d.path());
        assert_eq!(s.model, "claude-opus-5-5");
        assert_eq!(s.default_cta, "BẤM GIỎ HÀNG 👇");
        assert_eq!(s.voice_id, None);
        // a settings file from v0.3 with the removed length preset still loads
        std::fs::write(d.path().join("settings.json"), r#"{"defaultLength":"short","defaultCta":"MUA"}"#).unwrap();
        assert_eq!(load(d.path()).default_cta, "MUA");
    }
    #[test]
    fn new_fields_roundtrip_camel_case() {
        let d = tempfile::tempdir().unwrap();
        let s = Settings {
            voice_id: Some("v1".into()),
            voice_name: Some("Lan".into()),
            default_logo: Some("/data/defaults/logo.png".into()),
            default_cta: "MUA NGAY".into(),
            ..Default::default()
        };
        save(d.path(), &s).unwrap();
        let raw = std::fs::read_to_string(d.path().join("settings.json")).unwrap();
        for k in ["\"voiceId\"", "\"voiceName\"", "\"defaultLogo\"", "\"defaultCta\""] {
            assert!(raw.contains(k), "{k}");
        }
        assert_eq!(load(d.path()), s);
    }
}
