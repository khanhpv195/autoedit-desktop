use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::path::{Path, PathBuf};

use crate::settings::{DEFAULT_CTA, DEFAULT_LENGTH};

pub const NICHES: [&str; 5] = ["thoi-trang", "my-pham", "do-an", "phu-kien", "chung"];
pub const LENGTHS: [&str; 3] = ["short", "medium", "long"];
pub const MAX_PRODUCT_INFO: usize = 500;
const MAX_CTA: usize = 30;

/// Per-project voiceover choice. Stored in project.json with snake_case keys (engine contract),
/// sent to the UI in camelCase.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Voiceover {
    pub enabled: bool,
    pub voice_id: String,
    pub voice_name: String,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectSummary {
    pub dir: String,
    pub title: String,
    pub niche: String,
    pub created: String,
    pub status: String,
    pub run_count: usize,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Run {
    pub n: u64,
    #[serde(rename = "final")]
    pub final_path: String,
    pub prompt: String,
    pub feedback: Option<String>,
    pub summary: Vec<String>,
    pub needs_review: bool,
    pub fallback: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectDetail {
    #[serde(flatten)]
    pub summary: ProjectSummary,
    pub clips: Vec<String>,
    pub images: Vec<String>,
    pub logo: Option<String>,
    pub music: Option<String>,
    pub prompt: String,
    pub script_card: Option<Value>,
    pub runs: Vec<Run>,
    pub posts: Vec<Value>,
    pub cta_text: String,
    pub length: String,
    pub voiceover: Option<Voiceover>,
    pub product_info: String,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct FeedItem {
    pub text: String,
    pub tool: Option<String>,
}

const VI: [(&str, char); 7] = [
    ("àáảãạăằắẳẵặâầấẩẫậ", 'a'),
    ("èéẻẽẹêềếểễệ", 'e'),
    ("ìíỉĩị", 'i'),
    ("òóỏõọôồốổỗộơờớởỡợ", 'o'),
    ("ùúủũụưừứửữự", 'u'),
    ("ỳýỷỹỵ", 'y'),
    ("đ", 'd'),
];

pub fn slugify(name: &str) -> String {
    let mut out = String::new();
    for c in name.to_lowercase().chars() {
        let c = VI.iter().find(|(set, _)| set.contains(c)).map_or(c, |(_, base)| *base);
        if c.is_ascii_alphanumeric() {
            out.push(c);
        } else if !out.ends_with('-') {
            out.push('-');
        }
    }
    let slug: String = out.trim_matches('-').chars().take(40).collect();
    let slug = slug.trim_matches('-').to_string();
    if slug.is_empty() { "video".into() } else { slug }
}

fn read_json(dir: &Path) -> Result<Map<String, Value>, String> {
    let raw = std::fs::read_to_string(dir.join("project.json")).map_err(|e| format!("Không đọc được project: {e}"))?;
    match serde_json::from_str::<Value>(&raw) {
        Ok(Value::Object(m)) => Ok(m),
        _ => Err("project.json bị hỏng".into()),
    }
}

fn write_json(dir: &Path, m: &Map<String, Value>) -> Result<(), String> {
    let tmp = dir.join("project.json.tmp");
    let text = serde_json::to_string_pretty(m).map_err(|e| e.to_string())?;
    std::fs::write(&tmp, text).map_err(|e| e.to_string())?;
    std::fs::rename(&tmp, dir.join("project.json")).map_err(|e| e.to_string())
}

/// Run `f` holding the same exclusive lock the engine takes (`project.json.lock`, flock / LockFileEx on the
/// whole file), so Rust and engine read-modify-write cycles of project.json never interleave.
fn with_lock<T>(dir: &Path, f: impl FnOnce() -> Result<T, String>) -> Result<T, String> {
    let file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join("project.json.lock"))
        .map_err(|e| format!("Không khóa được project: {e}"))?;
    file.lock().map_err(|e| format!("Không khóa được project: {e}"))?;
    let out = f();
    let _ = file.unlock();
    out
}

/// A plain file name: no separators, not `.`/`..`, not absolute.
fn is_plain_name(n: &str) -> bool {
    !n.is_empty() && Path::new(n).file_name().is_some_and(|f| f == std::ffi::OsStr::new(n))
}

pub const MAX_CLIPS: usize = 10;
pub const MAX_IMAGES: usize = 20;

/// Copy `src` into `<dir>/input/` under a unique name, unless it already lives there (then keep it by name).
fn place_input(dir: &Path, src: &Path) -> Result<String, String> {
    let name = src.file_name().ok_or("Đường dẫn không hợp lệ")?;
    if !is_plain_name(&name.to_string_lossy()) {
        return Err("Tên file không hợp lệ".into());
    }
    let input = dir.join("input");
    std::fs::create_dir_all(&input).map_err(|e| e.to_string())?;
    let same_dir = |a: &Path, b: &Path| match (a.canonicalize(), b.canonicalize()) {
        (Ok(a), Ok(b)) => a == b,
        _ => a == b,
    };
    if src.parent().is_some_and(|p| same_dir(p, &input)) {
        return Ok(name.to_string_lossy().into_owned());
    }
    let stem = Path::new(name).file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
    let ext = Path::new(name).extension().map(|e| format!(".{}", e.to_string_lossy())).unwrap_or_default();
    let mut final_name = name.to_string_lossy().into_owned();
    let mut k = 2;
    while input.join(&final_name).exists() {
        final_name = format!("{stem}-{k}{ext}");
        k += 1;
    }
    std::fs::copy(src, input.join(&final_name)).map_err(|e| format!("Không chép được {}: {e}", src.display()))?;
    Ok(final_name)
}

fn validate_media(clips: &[PathBuf], images: &[PathBuf]) -> Result<(), String> {
    if clips.is_empty() {
        return Err("Cần ít nhất 1 clip".into());
    }
    if clips.len() > MAX_CLIPS {
        return Err(format!("Tối đa {MAX_CLIPS} clip"));
    }
    if images.len() > MAX_IMAGES {
        return Err(format!("Tối đa {MAX_IMAGES} ảnh"));
    }
    if let Some(p) = clips.iter().chain(images).find(|p| !p.is_file()) {
        return Err(format!("Không thấy file {}", p.display()));
    }
    Ok(())
}

fn place_media(dir: &Path, clips: &[PathBuf], images: &[PathBuf]) -> Result<(Vec<String>, Vec<String>), String> {
    validate_media(clips, images)?;
    let c = clips.iter().map(|p| place_input(dir, p)).collect::<Result<Vec<_>, _>>()?;
    let i = images.iter().map(|p| place_input(dir, p)).collect::<Result<Vec<_>, _>>()?;
    Ok((c, i))
}

/// CTA of 1–30 characters after trimming, else the default.
fn clean_cta(s: &str) -> String {
    let t = s.trim();
    let n = t.chars().count();
    if (1..=MAX_CTA).contains(&n) { t.to_string() } else { DEFAULT_CTA.to_string() }
}

fn clean_length(s: &str) -> String {
    if LENGTHS.contains(&s) { s.to_string() } else { DEFAULT_LENGTH.to_string() }
}

#[allow(clippy::too_many_arguments)]
pub fn create(
    root: &Path,
    niche: &str,
    clips: &[PathBuf],
    images: &[PathBuf],
    logo: Option<&Path>,
    music: Option<&Path>,
    cta_text: &str,
    length: &str,
    today: &str,
) -> Result<ProjectSummary, String> {
    if !NICHES.contains(&niche) {
        return Err(format!("Ngành không hợp lệ: {niche}"));
    }
    let first = clips.first().ok_or("Cần ít nhất 1 clip")?;
    validate_media(clips, images)?;
    if let Some(p) = logo.into_iter().chain(music).find(|p| !p.is_file()) {
        return Err(format!("Không thấy file {}", p.display()));
    }
    let stem = first.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
    let base = format!("{today}_{}", slugify(&stem));
    let mut dir = root.join(&base);
    let mut k = 2;
    while dir.exists() {
        dir = root.join(format!("{base}-{k}"));
        k += 1;
    }
    std::fs::create_dir_all(dir.join("input")).map_err(|e| e.to_string())?;
    let built = (|| {
        let (clip_names, image_names) = place_media(&dir, clips, images)?;
        let logo_name = logo.map(|p| place_input(&dir, p)).transpose()?;
        let music_name = music.map(|p| place_input(&dir, p)).transpose()?;
        let mut m = Map::new();
        m.insert("niche".into(), json!(niche));
        m.insert("clips".into(), json!(clip_names));
        m.insert("images".into(), json!(image_names));
        m.insert("logo".into(), json!(logo_name));
        m.insert("music".into(), json!(music_name));
        m.insert("prompt".into(), json!(""));
        m.insert("script_card".into(), Value::Null);
        m.insert("runs".into(), json!([]));
        m.insert("cta_text".into(), json!(clean_cta(cta_text)));
        m.insert("length".into(), json!(clean_length(length)));
        write_json(&dir, &m)?;
        summary(&dir, &m)
    })();
    if built.is_err() {
        let _ = std::fs::remove_dir_all(&dir);
    }
    built
}

fn summary(dir: &Path, m: &Map<String, Value>) -> Result<ProjectSummary, String> {
    let name = dir.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let title = name.split_once('_').map_or(name.clone(), |(_, t)| t.to_string());
    let created: String = name.chars().take(10).collect();
    let runs = m.get("runs").and_then(Value::as_array).cloned().unwrap_or_default();
    let status = match runs.last() {
        None => "new",
        Some(r) if r.get("needs_review").and_then(Value::as_bool).unwrap_or(false) => "needs_review",
        Some(_) => "done",
    };
    Ok(ProjectSummary {
        dir: dir.to_string_lossy().into_owned(),
        title,
        niche: m.get("niche").and_then(Value::as_str).unwrap_or("chung").to_string(),
        created,
        status: status.into(),
        run_count: runs.len(),
    })
}

pub fn list(root: &Path) -> Vec<ProjectSummary> {
    let Ok(rd) = std::fs::read_dir(root) else { return vec![] };
    let mut dirs: Vec<PathBuf> = rd.filter_map(Result::ok).map(|e| e.path()).filter(|p| p.is_dir()).collect();
    // Newest first: date prefix, then creation time (falls back to mtime) within the same day.
    let born = |p: &Path| {
        std::fs::metadata(p).ok().and_then(|m| m.created().or_else(|_| m.modified()).ok())
    };
    let day = |p: &PathBuf| p.file_name().map(|n| n.to_string_lossy().chars().take(10).collect::<String>());
    dirs.sort_by(|a, b| day(b).cmp(&day(a)).then_with(|| born(b).cmp(&born(a))).then_with(|| b.file_name().cmp(&a.file_name())));
    dirs.iter().filter_map(|d| read_json(d).ok().and_then(|m| summary(d, &m).ok())).collect()
}

fn opt_str(m: &Map<String, Value>, k: &str) -> Option<String> {
    m.get(k).and_then(Value::as_str).filter(|s| !s.is_empty()).map(String::from)
}

/// File names stored under `key`; `clips` falls back to the legacy single `clip` field.
fn names(m: &Map<String, Value>, key: &str) -> Vec<String> {
    let list = m.get(key).and_then(Value::as_array).map(|a| {
        a.iter().filter_map(|v| v.as_str().filter(|s| is_plain_name(s)).map(String::from)).collect::<Vec<_>>()
    });
    match list {
        Some(l) => l,
        None if key == "clips" => opt_str(m, "clip").filter(|s| is_plain_name(s)).into_iter().collect(),
        None => vec![],
    }
}

pub fn detail(dir: &Path) -> Result<ProjectDetail, String> {
    let m = read_json(dir)?;
    let input = dir.join("input");
    let abs_list = |k: &str| -> Vec<String> {
        names(&m, k).iter().map(|n| input.join(n).to_string_lossy().into_owned()).collect()
    };
    let abs_input = |k: &str| opt_str(&m, k).filter(|n| is_plain_name(n)).map(|n| input.join(n).to_string_lossy().into_owned());
    let runs = m
        .get("runs")
        .and_then(Value::as_array)
        .map(|rs| {
            rs.iter()
                .map(|r| {
                    let fin = r.get("final").and_then(Value::as_str).unwrap_or("");
                    let final_path = if Path::new(fin).is_absolute() { PathBuf::from(fin) } else { dir.join(fin) };
                    Run {
                        n: r.get("n").and_then(Value::as_u64).unwrap_or(0),
                        final_path: final_path.to_string_lossy().into_owned(),
                        prompt: r.get("prompt").and_then(Value::as_str).unwrap_or("").into(),
                        feedback: r.get("feedback").and_then(Value::as_str).map(String::from),
                        summary: r
                            .get("summary")
                            .and_then(Value::as_array)
                            .map(|a| a.iter().filter_map(|s| s.as_str().map(String::from)).collect())
                            .unwrap_or_default(),
                        needs_review: r.get("needs_review").and_then(Value::as_bool).unwrap_or(false),
                        fallback: r.get("fallback").and_then(Value::as_bool).unwrap_or(false),
                    }
                })
                .collect()
        })
        .unwrap_or_default();
    Ok(ProjectDetail {
        summary: summary(dir, &m)?,
        clips: abs_list("clips"),
        images: abs_list("images"),
        logo: abs_input("logo"),
        music: abs_input("music"),
        prompt: opt_str(&m, "prompt").unwrap_or_default(),
        script_card: m.get("script_card").filter(|v| !v.is_null()).cloned(),
        runs,
        posts: m.get("posts").and_then(Value::as_array).cloned().unwrap_or_default(),
        cta_text: clean_cta(m.get("cta_text").and_then(Value::as_str).unwrap_or("")),
        length: clean_length(m.get("length").and_then(Value::as_str).unwrap_or("")),
        voiceover: read_voiceover(&m),
        product_info: m.get("product_info").and_then(Value::as_str).unwrap_or("").to_string(),
    })
}

fn read_voiceover(m: &Map<String, Value>) -> Option<Voiceover> {
    let v = m.get("voiceover")?.as_object()?;
    Some(Voiceover {
        enabled: v.get("enabled").and_then(Value::as_bool).unwrap_or(false),
        voice_id: v.get("voice_id").and_then(Value::as_str).unwrap_or("").to_string(),
        voice_name: v.get("voice_name").and_then(Value::as_str).unwrap_or("").to_string(),
    })
}

/// Write `voiceover` (null when off) and `product_info` (trimmed, at most 500 characters) under the project lock.
pub fn set_voiceover(dir: &Path, voiceover: Option<Voiceover>, product_info: &str) -> Result<ProjectDetail, String> {
    let vo = match voiceover {
        Some(v) if v.enabled && v.voice_id.trim().is_empty() => return Err("Chưa chọn giọng đọc".into()),
        Some(v) => json!({ "enabled": v.enabled, "voice_id": v.voice_id.trim(), "voice_name": v.voice_name }),
        None => Value::Null,
    };
    let info: String = product_info.trim().chars().take(MAX_PRODUCT_INFO).collect();
    with_lock(dir, || {
        let mut m = read_json(dir)?;
        m.insert("voiceover".into(), vo);
        m.insert("product_info".into(), json!(info));
        write_json(dir, &m)
    })?;
    detail(dir)
}

pub fn update(dir: &Path, patch: &Value) -> Result<(), String> {
    let Some(p) = patch.as_object() else { return Err("patch không hợp lệ".into()) };
    with_lock(dir, || {
        let mut m = read_json(dir)?;
        for key in ["niche", "prompt", "script_card", "length"] {
            let Some(v) = p.get(key) else { continue };
            if key == "niche" && !v.as_str().is_some_and(|n| NICHES.contains(&n)) {
                return Err("Ngành không hợp lệ".into());
            }
            if key == "length" && !v.as_str().is_some_and(|n| LENGTHS.contains(&n)) {
                return Err("Độ dài không hợp lệ".into());
            }
            m.insert(key.into(), v.clone());
        }
        write_json(dir, &m)
    })
}

pub fn set_asset(dir: &Path, kind: &str, path: Option<&Path>) -> Result<ProjectDetail, String> {
    if kind != "logo" && kind != "music" {
        return Err(format!("Loại không hợp lệ: {kind}"));
    }
    read_json(dir)?;
    // Copy first (can take seconds); only the short read-modify-write holds the lock.
    let value = match path {
        Some(p) => json!(place_input(dir, p)?),
        None => Value::Null,
    };
    with_lock(dir, || {
        let mut m = read_json(dir)?;
        m.insert(kind.into(), value);
        write_json(dir, &m)
    })?;
    detail(dir)
}

pub fn set_media(dir: &Path, clips: &[PathBuf], images: &[PathBuf]) -> Result<ProjectDetail, String> {
    read_json(dir)?;
    let (c, i) = place_media(dir, clips, images)?;
    with_lock(dir, || {
        let mut m = read_json(dir)?;
        m.insert("clips".into(), json!(c));
        m.insert("images".into(), json!(i));
        m.remove("clip");
        write_json(dir, &m)
    })?;
    detail(dir)
}

pub fn run_feed(dir: &Path, n: u64) -> Vec<FeedItem> {
    let Ok(text) = std::fs::read_to_string(dir.join("runs").join(n.to_string()).join("agent.jsonl")) else {
        return vec![];
    };
    text.lines()
        .filter_map(|l| serde_json::from_str::<Value>(l).ok())
        .filter(|v| v.get("type").and_then(Value::as_str) == Some("agent"))
        .map(|v| FeedItem {
            text: v.get("text").and_then(Value::as_str).unwrap_or("").into(),
            tool: v.get("tool").and_then(Value::as_str).map(String::from),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn touch(p: &Path) {
        std::fs::write(p, b"x").unwrap();
    }
    fn new_project(root: &Path, cta: &str, length: &str) -> PathBuf {
        let clip = root.join("c.mp4");
        touch(&clip);
        let projects = root.join("p");
        std::fs::create_dir_all(&projects).unwrap();
        PathBuf::from(create(&projects, "chung", &[clip], &[], None, None, cta, length, "2026-11-20").unwrap().dir)
    }
    fn raw(dir: &Path) -> Value {
        serde_json::from_str(&std::fs::read_to_string(dir.join("project.json")).unwrap()).unwrap()
    }
    #[test]
    fn create_writes_cta_and_length() {
        let root = tempfile::tempdir().unwrap();
        let dir = new_project(root.path(), "  MUA NGAY 👇 ", "short");
        let j = raw(&dir);
        assert_eq!(j["cta_text"], "MUA NGAY 👇");
        assert_eq!(j["length"], "short");
        let d = detail(&dir).unwrap();
        assert_eq!((d.cta_text.as_str(), d.length.as_str()), ("MUA NGAY 👇", "short"));
        assert_eq!(d.voiceover, None);
        assert_eq!(d.product_info, "");
    }
    #[test]
    fn create_falls_back_to_defaults_for_bad_values() {
        let root = tempfile::tempdir().unwrap();
        let dir = new_project(root.path(), "   ", "huge");
        assert_eq!(raw(&dir)["cta_text"], "BẤM GIỎ HÀNG 👇");
        assert_eq!(raw(&dir)["length"], "medium");
        let dir = new_project(root.path(), &"x".repeat(31), "long");
        assert_eq!(raw(&dir)["cta_text"], "BẤM GIỎ HÀNG 👇");
        assert_eq!(raw(&dir)["length"], "long");
        // 30 characters (an emoji counts as one) is still fine
        let thirty = format!("{}👇", "a".repeat(29));
        assert_eq!(raw(&new_project(root.path(), &thirty, "medium"))["cta_text"], thirty.as_str());
    }
    #[test]
    fn old_project_detail_reads_defaults() {
        let root = tempfile::tempdir().unwrap();
        let dir = root.path().join("2026-11-01_old");
        std::fs::create_dir_all(dir.join("input")).unwrap();
        std::fs::write(dir.join("project.json"), r#"{"niche":"chung","clips":["a.mp4"],"prompt":"","runs":[]}"#).unwrap();
        let d = detail(&dir).unwrap();
        assert_eq!(d.cta_text, "BẤM GIỎ HÀNG 👇");
        assert_eq!(d.length, "medium");
        assert_eq!(d.voiceover, None);
        assert_eq!(d.product_info, "");
        // garbage values also read as defaults
        std::fs::write(dir.join("project.json"), r#"{"niche":"chung","cta_text":"","length":"xl","voiceover":"on","product_info":5}"#).unwrap();
        let d = detail(&dir).unwrap();
        assert_eq!((d.cta_text.as_str(), d.length.as_str(), d.product_info.as_str()), ("BẤM GIỎ HÀNG 👇", "medium", ""));
        assert_eq!(d.voiceover, None);
    }
    #[test]
    fn set_project_voiceover_writes_keys_and_truncates_info() {
        let root = tempfile::tempdir().unwrap();
        let dir = new_project(root.path(), "", "");
        update(&dir, &json!({"prompt": "giữ"})).unwrap();
        let vo = Voiceover { enabled: true, voice_id: "v1".into(), voice_name: "Lan".into() };
        let info = "ạ".repeat(600);
        let d = set_voiceover(&dir, Some(vo.clone()), &info).unwrap();
        let j = raw(&dir);
        assert_eq!(j["voiceover"], json!({"enabled": true, "voice_id": "v1", "voice_name": "Lan"}));
        assert_eq!(j["product_info"].as_str().unwrap().chars().count(), 500);
        assert_eq!(j["prompt"], "giữ");
        assert_eq!(d.voiceover, Some(vo));
        assert_eq!(serde_json::to_value(&d).unwrap()["voiceover"], json!({"enabled": true, "voiceId": "v1", "voiceName": "Lan"}));
        // turned off: stored as null, product info kept
        let d = set_voiceover(&dir, None, " áo lụa ").unwrap();
        assert!(raw(&dir)["voiceover"].is_null());
        assert_eq!(d.product_info, "áo lụa");
        // enabled without a voice is refused
        let bad = Voiceover { enabled: true, voice_id: " ".into(), voice_name: "".into() };
        assert!(set_voiceover(&dir, Some(bad), "").is_err());
    }
    #[test]
    fn set_project_voiceover_waits_for_the_project_lock() {
        let root = tempfile::tempdir().unwrap();
        let dir = new_project(root.path(), "", "");
        let (tx, rx) = std::sync::mpsc::channel();
        let held = dir.clone();
        let holder = std::thread::spawn(move || {
            with_lock(&held, || {
                tx.send(()).unwrap();
                std::thread::sleep(std::time::Duration::from_millis(300));
                // an engine-style write while the lock is held must survive
                let mut m = read_json(&held)?;
                m.insert("prompt".into(), json!("engine"));
                write_json(&held, &m)
            })
            .unwrap()
        });
        rx.recv().unwrap();
        let t0 = std::time::Instant::now();
        let vo = Voiceover { enabled: true, voice_id: "v1".into(), voice_name: "Lan".into() };
        set_voiceover(&dir, Some(vo), "info").unwrap();
        assert!(t0.elapsed() >= std::time::Duration::from_millis(200), "did not wait for the lock");
        holder.join().unwrap();
        let j = raw(&dir);
        assert_eq!(j["prompt"], "engine");
        assert_eq!(j["product_info"], "info");
    }
    #[test]
    fn update_accepts_a_valid_length_only() {
        let root = tempfile::tempdir().unwrap();
        let dir = new_project(root.path(), "", "");
        update(&dir, &json!({"length": "long"})).unwrap();
        assert_eq!(detail(&dir).unwrap().length, "long");
        assert!(update(&dir, &json!({"length": "xl"})).is_err());
        assert_eq!(raw(&dir)["length"], "long");
    }
    #[test]
    fn slug_strips_vietnamese() {
        assert_eq!(slugify("Quần Ống Rộng #1"), "quan-ong-rong-1");
        assert_eq!(slugify("!!!"), "video");
    }
    #[test]
    fn create_copies_inputs_and_writes_engine_json() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let clip = src.path().join("Váy đỏ.mp4");
        touch(&clip);
        let logo = src.path().join("logo.png");
        touch(&logo);
        let s = create(root.path(), "thoi-trang", std::slice::from_ref(&clip), &[], Some(&logo), None, "", "", "2026-11-20").unwrap();
        assert!(s.dir.ends_with("2026-11-20_vay-do"));
        let j: Value =
            serde_json::from_str(&std::fs::read_to_string(Path::new(&s.dir).join("project.json")).unwrap()).unwrap();
        assert_eq!(j["clips"], json!(["Váy đỏ.mp4"]));
        assert!(j.get("clip").is_none());
        assert_eq!(j["logo"], "logo.png");
        assert!(j["music"].is_null());
        assert!(Path::new(&s.dir).join("input/Váy đỏ.mp4").exists());
        let s2 = create(root.path(), "thoi-trang", std::slice::from_ref(&clip), &[], None, None, "", "", "2026-11-20").unwrap();
        assert!(s2.dir.ends_with("2026-11-20_vay-do-2"));
    }
    #[test]
    fn list_orders_same_day_newest_first_not_by_slug() {
        let root = tempfile::tempdir().unwrap();
        let clip = root.path().join("c.mp4");
        touch(&clip);
        let projects = root.path().join("p");
        std::fs::create_dir_all(&projects).unwrap();
        create(&projects, "chung", std::slice::from_ref(&clip), &[], None, None, "", "", "2026-11-20").unwrap();
        std::thread::sleep(std::time::Duration::from_millis(30));
        let second = root.path().join("a.mp4");
        touch(&second);
        create(&projects, "chung", std::slice::from_ref(&second), &[], None, None, "", "", "2026-11-20").unwrap();
        std::thread::sleep(std::time::Duration::from_millis(30));
        create(&projects, "chung", std::slice::from_ref(&clip), &[], None, None, "", "", "2026-11-19").unwrap();
        let titles: Vec<String> = list(&projects).into_iter().map(|p| p.dir.rsplit('/').next().unwrap().to_string()).collect();
        assert_eq!(titles, vec!["2026-11-20_a", "2026-11-20_c", "2026-11-19_c"]);
    }
    #[test]
    fn create_rejects_bad_niche() {
        let src = tempfile::tempdir().unwrap();
        let clip = src.path().join("a.mp4");
        touch(&clip);
        assert!(create(src.path(), "xe-hoi", std::slice::from_ref(&clip), &[], None, None, "", "", "2026-11-20").is_err());
    }
    #[test]
    fn update_keeps_unknown_keys_and_ignores_disallowed() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let clip = src.path().join("a.mp4");
        touch(&clip);
        let s = create(root.path(), "do-an", std::slice::from_ref(&clip), &[], None, None, "", "", "2026-11-20").unwrap();
        update(Path::new(&s.dir), &json!({"prompt": "ngắn gọn", "runs": "hack"})).unwrap();
        let d = detail(Path::new(&s.dir)).unwrap();
        assert_eq!(d.prompt, "ngắn gọn");
        assert!(d.runs.is_empty());
    }
    #[test]
    fn set_asset_sets_and_clears() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let clip = src.path().join("a.mp4");
        touch(&clip);
        let song = src.path().join("s.mp3");
        touch(&song);
        let s = create(root.path(), "do-an", std::slice::from_ref(&clip), &[], None, None, "", "", "2026-11-20").unwrap();
        let d = set_asset(Path::new(&s.dir), "music", Some(&song)).unwrap();
        assert!(d.music.unwrap().ends_with("input/s.mp3"));
        assert!(set_asset(Path::new(&s.dir), "music", None).unwrap().music.is_none());
        assert!(Path::new(&s.dir).join("input/s.mp3").exists());
    }
    #[test]
    fn status_and_feed_from_runs() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let clip = src.path().join("a.mp4");
        touch(&clip);
        let s = create(root.path(), "do-an", std::slice::from_ref(&clip), &[], None, None, "", "", "2026-11-20").unwrap();
        let dir = Path::new(&s.dir);
        let mut j: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("project.json")).unwrap()).unwrap();
        j["runs"] = json!([{"n":1,"final":"runs/1/final.mp4","prompt":"p","feedback":null,"summary":["s"],"needs_review":true,"fallback":false}]);
        std::fs::write(dir.join("project.json"), j.to_string()).unwrap();
        std::fs::create_dir_all(dir.join("runs/1")).unwrap();
        std::fs::write(
            dir.join("runs/1/agent.jsonl"),
            "{\"type\":\"agent\",\"text\":\"Cắt\",\"tool\":\"set_edl\"}\n{\"kind\":\"sdk\"}\n",
        )
        .unwrap();
        assert_eq!(list(root.path())[0].status, "needs_review");
        let d = detail(dir).unwrap();
        assert!(d.runs[0].final_path.ends_with("runs/1/final.mp4"));
        assert!(d.runs[0].needs_review);
        let v = serde_json::to_value(&d).unwrap();
        assert_eq!(v["runs"][0]["needsReview"], true);
        assert_eq!(v["runCount"], 1);
        assert_eq!(run_feed(dir, 1).len(), 1);
    }
    #[test]
    fn detail_exposes_posts() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let clip = src.path().join("a.mp4");
        touch(&clip);
        let s = create(root.path(), "do-an", std::slice::from_ref(&clip), &[], None, None, "", "", "2026-11-20").unwrap();
        let dir = Path::new(&s.dir);
        assert!(detail(dir).unwrap().posts.is_empty());
        let mut j: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("project.json")).unwrap()).unwrap();
        j["posts"] = json!([{"id":"p1","run":1,"postDate":"2026-11-21T19:30:00+07:00","channels":["TIKTOK"],"status":"SCHEDULED"}]);
        std::fs::write(dir.join("project.json"), j.to_string()).unwrap();
        let v = serde_json::to_value(detail(dir).unwrap()).unwrap();
        assert_eq!(v["posts"][0]["id"], "p1");
    }
    #[test]
    fn create_with_several_clips_and_images() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let mk = |n: &str| {
            let p = src.path().join(n);
            touch(&p);
            p
        };
        let (a, b, i1, i2) = (mk("a.mp4"), mk("b.mov"), mk("x.png"), mk("y.jpg"));
        let s = create(root.path(), "chung", &[b.clone(), a.clone()], &[i1, i2], None, None, "", "", "2026-11-20").unwrap();
        assert!(s.dir.ends_with("2026-11-20_b"));
        let d = detail(Path::new(&s.dir)).unwrap();
        let tail = |v: &[String]| v.iter().map(|p| p.rsplit('/').next().unwrap().to_string()).collect::<Vec<_>>();
        assert_eq!(tail(&d.clips), ["b.mov", "a.mp4"]);
        assert_eq!(tail(&d.images), ["x.png", "y.jpg"]);
        assert!(Path::new(&d.images[1]).exists());
        assert!(create(root.path(), "chung", &[], &[], None, None, "", "", "2026-11-20").is_err());
        let many: Vec<PathBuf> = (0..11).map(|_| a.clone()).collect();
        assert!(create(root.path(), "chung", &many, &[], None, None, "", "", "2026-11-20").is_err());
    }
    #[test]
    fn detail_reads_legacy_clip() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let clip = src.path().join("a.mp4");
        touch(&clip);
        let s = create(root.path(), "do-an", std::slice::from_ref(&clip), &[], None, None, "", "", "2026-11-20").unwrap();
        let dir = Path::new(&s.dir);
        let mut j: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("project.json")).unwrap()).unwrap();
        j.as_object_mut().unwrap().remove("clips");
        j.as_object_mut().unwrap().remove("images");
        j["clip"] = json!("a.mp4");
        std::fs::write(dir.join("project.json"), j.to_string()).unwrap();
        let d = detail(dir).unwrap();
        assert_eq!(d.clips.len(), 1);
        assert!(d.clips[0].ends_with("input/a.mp4"));
        assert!(d.images.is_empty());
    }
    #[test]
    fn set_media_keeps_inside_copies_outside_and_orders() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let mk = |n: &str| {
            let p = src.path().join(n);
            touch(&p);
            p
        };
        let (a, b, c, img) = (mk("a.mp4"), mk("b.mp4"), mk("c.mp4"), mk("p.png"));
        let s = create(root.path(), "chung", &[a.clone(), b.clone()], &[], None, None, "", "", "2026-11-20").unwrap();
        let dir = Path::new(&s.dir);
        // simulate a legacy leftover `clip` field
        let mut j: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("project.json")).unwrap()).unwrap();
        j["clip"] = json!("a.mp4");
        std::fs::write(dir.join("project.json"), j.to_string()).unwrap();
        let before = detail(dir).unwrap();
        let (ia, ib) = (PathBuf::from(&before.clips[0]), PathBuf::from(&before.clips[1]));
        // reorder (inside input -> kept); outside clip c and image copied; a same-named outside file gets a unique name
        let other = src.path().join("sub");
        std::fs::create_dir_all(&other).unwrap();
        let a2 = other.join("a.mp4");
        std::fs::write(&a2, b"different").unwrap();
        let d = set_media(dir, &[ib, ia, c, a2], &[img]).unwrap();
        let tail = |v: &[String]| v.iter().map(|p| p.rsplit('/').next().unwrap().to_string()).collect::<Vec<_>>();
        assert_eq!(tail(&d.clips), ["b.mp4", "a.mp4", "c.mp4", "a-2.mp4"]);
        assert_eq!(tail(&d.images), ["p.png"]);
        let j: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("project.json")).unwrap()).unwrap();
        assert!(j.get("clip").is_none());
        assert_eq!(std::fs::read_dir(dir.join("input")).unwrap().count(), 5);
        // dropping clips leaves their files on disk
        let d = set_media(dir, &[PathBuf::from(&d.clips[0])], &[]).unwrap();
        assert_eq!(d.clips.len(), 1);
        assert!(dir.join("input/c.mp4").exists());
        assert!(set_media(dir, &[], &[]).is_err());
    }
    #[test]
    fn concurrent_update_and_set_media_keep_both() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let clip = src.path().join("a.mp4");
        touch(&clip);
        let s = create(root.path(), "chung", std::slice::from_ref(&clip), &[], None, None, "", "", "2026-11-20").unwrap();
        let dir = PathBuf::from(&s.dir);
        let big = src.path().join("big.mp4");
        std::fs::write(&big, vec![1u8; 20_000_000]).unwrap();
        for n in 0..5 {
            let (d1, d2, c2, b2) = (dir.clone(), dir.clone(), clip.clone(), big.clone());
            let t1 = std::thread::spawn(move || set_media(&d1, &[c2, b2], &[]).unwrap());
            let t2 = std::thread::spawn(move || update(&d2, &json!({"prompt": format!("p{n}")})).unwrap());
            t1.join().unwrap();
            t2.join().unwrap();
            let d = detail(&dir).unwrap();
            assert_eq!(d.prompt, format!("p{n}"));
            assert_eq!(d.clips.len(), 2);
        }
    }
    #[test]
    fn set_media_keeps_prompt_written_during_copy() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let clip = src.path().join("a.mp4");
        touch(&clip);
        let s = create(root.path(), "chung", std::slice::from_ref(&clip), &[], None, None, "", "", "2026-11-20").unwrap();
        let dir = Path::new(&s.dir);
        let other = src.path().join("b.mp4");
        touch(&other);
        // the update lands between the (slow) copy phase and the json write
        let (c, i) = place_media(dir, &[clip.clone(), other], &[]).unwrap();
        update(dir, &json!({"prompt": "mới"})).unwrap();
        with_lock(dir, || {
            let mut m = read_json(dir)?;
            m.insert("clips".into(), json!(c));
            m.insert("images".into(), json!(i));
            write_json(dir, &m)
        })
        .unwrap();
        assert_eq!(detail(dir).unwrap().prompt, "mới");
    }
    #[test]
    fn logo_does_not_replace_broll_image_of_same_name() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let (clip, img) = (src.path().join("a.mp4"), src.path().join("1.jpg"));
        touch(&clip);
        std::fs::write(&img, b"broll").unwrap();
        let s = create(root.path(), "chung", &[clip], std::slice::from_ref(&img), None, None, "", "", "2026-11-20").unwrap();
        let dir = Path::new(&s.dir);
        let logo_dir = src.path().join("l");
        std::fs::create_dir_all(&logo_dir).unwrap();
        let logo = logo_dir.join("1.jpg");
        std::fs::write(&logo, b"logo").unwrap();
        let d = set_asset(dir, "logo", Some(&logo)).unwrap();
        assert!(d.logo.unwrap().ends_with("1-2.jpg"));
        assert_eq!(std::fs::read(dir.join("input/1.jpg")).unwrap(), b"broll");
    }
    #[test]
    fn failed_create_leaves_no_directory() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let clip = src.path().join("a.mp4");
        touch(&clip);
        let missing = src.path().join("nope.png");
        assert!(create(root.path(), "chung", std::slice::from_ref(&clip), &[], Some(&missing), None, "", "", "2026-11-20").is_err());
        let many: Vec<PathBuf> = (0..21).map(|_| clip.clone()).collect();
        assert!(create(root.path(), "chung", std::slice::from_ref(&clip), &many, None, None, "", "", "2026-11-20").is_err());
        assert_eq!(std::fs::read_dir(root.path()).unwrap().count(), 0);
        // a failure after the dir exists (a directory named like a clip is not a file) is cleaned up too
        let ok2 = src.path().join("b.mp4");
        touch(&ok2);
        let sub = src.path().join("sub");
        std::fs::create_dir_all(&sub).unwrap();
        let bad_logo = sub.join("logo.png");
        std::fs::write(&bad_logo, b"x").unwrap();
        let mut perms = std::fs::metadata(&bad_logo).unwrap().permissions();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            perms.set_mode(0o000);
            std::fs::set_permissions(&bad_logo, perms).unwrap();
            if std::fs::File::open(&bad_logo).is_err() {
                assert!(create(root.path(), "chung", &[ok2], &[], Some(&bad_logo), None, "", "", "2026-11-20").is_err());
                assert_eq!(std::fs::read_dir(root.path()).unwrap().count(), 0);
            }
        }
        #[cfg(not(unix))]
        let _ = &mut perms;
    }
    #[test]
    fn detail_skips_non_plain_names() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let clip = src.path().join("a.mp4");
        touch(&clip);
        let s = create(root.path(), "chung", std::slice::from_ref(&clip), &[], None, None, "", "", "2026-11-20").unwrap();
        let dir = Path::new(&s.dir);
        let mut j: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("project.json")).unwrap()).unwrap();
        j["clips"] = json!(["a.mp4", "../../etc/passwd", "/abs.mp4", "sub/x.mp4", ".."]);
        j["logo"] = json!("../x.png");
        j["music"] = json!("m.mp3");
        std::fs::write(dir.join("project.json"), j.to_string()).unwrap();
        let d = detail(dir).unwrap();
        assert_eq!(d.clips.len(), 1);
        assert!(d.logo.is_none());
        assert!(d.music.unwrap().ends_with("input/m.mp3"));
    }
}
