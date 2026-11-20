use serde::Serialize;
use serde_json::{Map, Value, json};
use std::path::{Path, PathBuf};

pub const NICHES: [&str; 5] = ["thoi-trang", "my-pham", "do-an", "phu-kien", "chung"];

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
    pub clip: String,
    pub logo: Option<String>,
    pub music: Option<String>,
    pub prompt: String,
    pub script_card: Option<Value>,
    pub runs: Vec<Run>,
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

fn copy_input(dir: &Path, src: &Path) -> Result<String, String> {
    let name = src.file_name().ok_or("Đường dẫn không hợp lệ")?;
    let input = dir.join("input");
    std::fs::create_dir_all(&input).map_err(|e| e.to_string())?;
    let dest = input.join(name);
    if dest != src {
        std::fs::copy(src, &dest).map_err(|e| format!("Không chép được {}: {e}", src.display()))?;
    }
    Ok(name.to_string_lossy().into_owned())
}

pub fn create(
    root: &Path,
    niche: &str,
    clip: &Path,
    logo: Option<&Path>,
    music: Option<&Path>,
    today: &str,
) -> Result<ProjectSummary, String> {
    if !NICHES.contains(&niche) {
        return Err(format!("Ngành không hợp lệ: {niche}"));
    }
    if !clip.is_file() {
        return Err("Không thấy file clip".into());
    }
    let stem = clip.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
    let base = format!("{today}_{}", slugify(&stem));
    let mut dir = root.join(&base);
    let mut k = 2;
    while dir.exists() {
        dir = root.join(format!("{base}-{k}"));
        k += 1;
    }
    std::fs::create_dir_all(dir.join("input")).map_err(|e| e.to_string())?;
    let clip_name = copy_input(&dir, clip)?;
    let logo_name = logo.map(|p| copy_input(&dir, p)).transpose()?;
    let music_name = music.map(|p| copy_input(&dir, p)).transpose()?;
    let mut m = Map::new();
    m.insert("niche".into(), json!(niche));
    m.insert("clip".into(), json!(clip_name));
    m.insert("logo".into(), json!(logo_name));
    m.insert("music".into(), json!(music_name));
    m.insert("prompt".into(), json!(""));
    m.insert("script_card".into(), Value::Null);
    m.insert("runs".into(), json!([]));
    write_json(&dir, &m)?;
    summary(&dir, &m)
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
    dirs.sort_by(|a, b| b.file_name().cmp(&a.file_name()));
    dirs.iter().filter_map(|d| read_json(d).ok().and_then(|m| summary(d, &m).ok())).collect()
}

fn opt_str(m: &Map<String, Value>, k: &str) -> Option<String> {
    m.get(k).and_then(Value::as_str).filter(|s| !s.is_empty()).map(String::from)
}

pub fn detail(dir: &Path) -> Result<ProjectDetail, String> {
    let m = read_json(dir)?;
    let input = dir.join("input");
    let abs_input = |k: &str| opt_str(&m, k).map(|n| input.join(n).to_string_lossy().into_owned());
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
        clip: abs_input("clip").unwrap_or_default(),
        logo: abs_input("logo"),
        music: abs_input("music"),
        prompt: opt_str(&m, "prompt").unwrap_or_default(),
        script_card: m.get("script_card").filter(|v| !v.is_null()).cloned(),
        runs,
    })
}

pub fn update(dir: &Path, patch: &Value) -> Result<(), String> {
    let mut m = read_json(dir)?;
    let Some(p) = patch.as_object() else { return Err("patch không hợp lệ".into()) };
    for key in ["niche", "prompt", "script_card"] {
        let Some(v) = p.get(key) else { continue };
        if key == "niche" && !v.as_str().is_some_and(|n| NICHES.contains(&n)) {
            return Err("Ngành không hợp lệ".into());
        }
        m.insert(key.into(), v.clone());
    }
    write_json(dir, &m)
}

pub fn set_asset(dir: &Path, kind: &str, path: Option<&Path>) -> Result<ProjectDetail, String> {
    if kind != "logo" && kind != "music" {
        return Err(format!("Loại không hợp lệ: {kind}"));
    }
    let mut m = read_json(dir)?;
    let value = match path {
        Some(p) => json!(copy_input(dir, p)?),
        None => Value::Null,
    };
    m.insert(kind.into(), value);
    write_json(dir, &m)?;
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
        let s = create(root.path(), "thoi-trang", &clip, Some(&logo), None, "2026-11-20").unwrap();
        assert!(s.dir.ends_with("2026-11-20_vay-do"));
        let j: Value =
            serde_json::from_str(&std::fs::read_to_string(Path::new(&s.dir).join("project.json")).unwrap()).unwrap();
        assert_eq!(j["clip"], "Váy đỏ.mp4");
        assert_eq!(j["logo"], "logo.png");
        assert!(j["music"].is_null());
        assert!(Path::new(&s.dir).join("input/Váy đỏ.mp4").exists());
        let s2 = create(root.path(), "thoi-trang", &clip, None, None, "2026-11-20").unwrap();
        assert!(s2.dir.ends_with("2026-11-20_vay-do-2"));
    }
    #[test]
    fn create_rejects_bad_niche() {
        let src = tempfile::tempdir().unwrap();
        let clip = src.path().join("a.mp4");
        touch(&clip);
        assert!(create(src.path(), "xe-hoi", &clip, None, None, "2026-11-20").is_err());
    }
    #[test]
    fn update_keeps_unknown_keys_and_ignores_disallowed() {
        let src = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        let clip = src.path().join("a.mp4");
        touch(&clip);
        let s = create(root.path(), "do-an", &clip, None, None, "2026-11-20").unwrap();
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
        let s = create(root.path(), "do-an", &clip, None, None, "2026-11-20").unwrap();
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
        let s = create(root.path(), "do-an", &clip, None, None, "2026-11-20").unwrap();
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
}
