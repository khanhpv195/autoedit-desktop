use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::collections::{HashMap, HashSet};
use std::path::Path;

use crate::secrets::SecretStore;

pub const MAX_SERVERS: usize = 10;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct McpServer {
    pub name: String,
    pub enabled: bool,
    pub transport: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub command: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub args: Option<Vec<String>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub env_keys: Option<Vec<String>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub header_keys: Option<Vec<String>>,
}

impl McpServer {
    fn secret_keys(&self) -> Vec<String> {
        let k = if self.transport == "stdio" { &self.env_keys } else { &self.header_keys };
        k.clone().unwrap_or_default()
    }
}

fn account(name: &str, key: &str) -> String {
    format!("mcp:{name}:{key}")
}

pub fn load(dir: &Path) -> Vec<McpServer> {
    std::fs::read_to_string(dir.join("mcp.json"))
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_default()
}

fn write(dir: &Path, servers: &[McpServer]) -> Result<(), String> {
    std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    let tmp = dir.join("mcp.json.tmp");
    std::fs::write(&tmp, serde_json::to_string_pretty(servers).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    std::fs::rename(&tmp, dir.join("mcp.json")).map_err(|e| e.to_string())
}

fn validate(s: &McpServer) -> Result<(), String> {
    let re = Regex::new(r"^[a-z0-9][a-z0-9-]{0,30}$").unwrap();
    if !re.is_match(&s.name) || s.name == "autoedit" {
        return Err("Tên MCP chỉ gồm chữ thường, số, dấu gạch ngang (tối đa 31 ký tự) và không được là autoedit".into());
    }
    match s.transport.as_str() {
        "stdio" => {
            if s.command.as_deref().map(str::trim).unwrap_or("").is_empty() {
                return Err("Thiếu lệnh chạy MCP".into());
            }
        }
        "http" => {
            let u = s.url.as_deref().unwrap_or("");
            if !(u.starts_with("http://") || u.starts_with("https://")) {
                return Err("URL MCP phải bắt đầu bằng http:// hoặc https://".into());
            }
        }
        _ => return Err("Loại MCP không hợp lệ".into()),
    }
    let keys = s.secret_keys();
    if keys.iter().any(|k| k.trim().is_empty()) || keys.iter().collect::<HashSet<_>>().len() != keys.len() {
        return Err("Tên khóa trống hoặc bị trùng".into());
    }
    Ok(())
}

/// Save (add or replace) a server. An empty secret value keeps the stored one.
pub fn save_server(
    dir: &Path,
    secrets: &dyn SecretStore,
    server: McpServer,
    secret_values: &HashMap<String, String>,
) -> Result<(), String> {
    validate(&server)?;
    let mut all = load(dir);
    let pos = all.iter().position(|s| s.name == server.name);
    if pos.is_none() && all.len() >= MAX_SERVERS {
        return Err(format!("Tối đa {MAX_SERVERS} MCP server"));
    }
    let new_keys: HashSet<String> = server.secret_keys().into_iter().collect();
    if let Some(i) = pos {
        for k in all[i].secret_keys() {
            if !new_keys.contains(&k) {
                secrets.delete(&account(&server.name, &k))?;
            }
        }
    }
    for k in &new_keys {
        if let Some(v) = secret_values.get(k).filter(|v| !v.is_empty()) {
            secrets.set(&account(&server.name, k), v)?;
        }
    }
    match pos {
        Some(i) => all[i] = server,
        None => all.push(server),
    }
    write(dir, &all)
}

pub fn delete(dir: &Path, secrets: &dyn SecretStore, name: &str) -> Result<(), String> {
    let mut all = load(dir);
    if let Some(i) = all.iter().position(|s| s.name == name) {
        let s = all.remove(i);
        for k in s.secret_keys() {
            secrets.delete(&account(name, &k))?;
        }
        write(dir, &all)?;
    }
    Ok(())
}

/// JSON for the engine env `AUTOEDIT_MCP`: enabled servers only, secrets filled from the store.
pub fn engine_json(dir: &Path, secrets: &dyn SecretStore) -> String {
    let mut out = Map::new();
    for s in load(dir).into_iter().filter(|s| s.enabled) {
        let mut kv = Map::new();
        for k in s.secret_keys() {
            if let Some(v) = secrets.get(&account(&s.name, &k)) {
                kv.insert(k, Value::String(v));
            }
        }
        let cfg = if s.transport == "stdio" {
            json!({"type": "stdio", "command": s.command, "args": s.args.clone().unwrap_or_default(), "env": kv})
        } else {
            json!({"type": "http", "url": s.url, "headers": kv})
        };
        out.insert(s.name.clone(), cfg);
    }
    Value::Object(out).to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::secrets::MemoryStore;

    fn stdio(name: &str) -> McpServer {
        McpServer {
            name: name.into(),
            enabled: true,
            transport: "stdio".into(),
            command: Some("npx".into()),
            args: Some(vec!["-y".into(), "srv".into()]),
            env_keys: Some(vec!["TOKEN".into()]),
            url: None,
            header_keys: None,
        }
    }
    fn http(name: &str, url: &str) -> McpServer {
        McpServer {
            name: name.into(),
            enabled: true,
            transport: "http".into(),
            command: None,
            args: None,
            env_keys: None,
            url: Some(url.into()),
            header_keys: Some(vec!["Authorization".into()]),
        }
    }
    fn sec(k: &str, v: &str) -> HashMap<String, String> {
        HashMap::from([(k.to_string(), v.to_string())])
    }

    #[test]
    fn rejects_bad_names_url_and_eleventh_server() {
        let d = tempfile::tempdir().unwrap();
        let m = MemoryStore::default();
        for bad in ["autoedit", "Bad Name", "-x", ""] {
            assert!(save_server(d.path(), &m, stdio(bad), &HashMap::new()).is_err(), "{bad}");
        }
        assert!(save_server(d.path(), &m, http("h", "ftp://x"), &HashMap::new()).is_err());
        for i in 0..10 {
            save_server(d.path(), &m, stdio(&format!("s{i}")), &HashMap::new()).unwrap();
        }
        assert!(save_server(d.path(), &m, stdio("s10"), &HashMap::new()).is_err());
        // replacing an existing one is still fine
        save_server(d.path(), &m, stdio("s3"), &HashMap::new()).unwrap();
        assert_eq!(load(d.path()).len(), 10);
    }

    #[test]
    fn secrets_go_to_store_not_to_file() {
        let d = tempfile::tempdir().unwrap();
        let m = MemoryStore::default();
        save_server(d.path(), &m, stdio("shop"), &sec("TOKEN", "s3cr3t-value")).unwrap();
        assert_eq!(m.get("mcp:shop:TOKEN").as_deref(), Some("s3cr3t-value"));
        let raw = std::fs::read_to_string(d.path().join("mcp.json")).unwrap();
        assert!(!raw.contains("s3cr3t-value"));
        assert!(raw.contains("TOKEN"));
    }

    #[test]
    fn empty_secret_keeps_old_and_removed_key_deletes() {
        let d = tempfile::tempdir().unwrap();
        let m = MemoryStore::default();
        save_server(d.path(), &m, stdio("shop"), &sec("TOKEN", "v1")).unwrap();
        save_server(d.path(), &m, stdio("shop"), &sec("TOKEN", "")).unwrap();
        assert_eq!(m.get("mcp:shop:TOKEN").as_deref(), Some("v1"));
        let mut s = stdio("shop");
        s.env_keys = Some(vec![]);
        save_server(d.path(), &m, s, &HashMap::new()).unwrap();
        assert_eq!(m.get("mcp:shop:TOKEN"), None);
    }

    #[test]
    fn engine_json_fills_secrets_and_skips_disabled() {
        let d = tempfile::tempdir().unwrap();
        let m = MemoryStore::default();
        save_server(d.path(), &m, stdio("shop"), &sec("TOKEN", "v1")).unwrap();
        save_server(d.path(), &m, http("web", "https://x.io/mcp"), &sec("Authorization", "Bearer z")).unwrap();
        let mut off = stdio("off");
        off.enabled = false;
        save_server(d.path(), &m, off, &sec("TOKEN", "zz")).unwrap();
        save_server(d.path(), &m, stdio("nokey"), &HashMap::new()).unwrap();
        let v: Value = serde_json::from_str(&engine_json(d.path(), &m)).unwrap();
        assert_eq!(v["shop"]["type"], "stdio");
        assert_eq!(v["shop"]["command"], "npx");
        assert_eq!(v["shop"]["args"][1], "srv");
        assert_eq!(v["shop"]["env"]["TOKEN"], "v1");
        assert_eq!(v["web"]["headers"]["Authorization"], "Bearer z");
        assert!(v.get("off").is_none());
        assert_eq!(v["nokey"]["env"], json!({}));
    }

    #[test]
    fn delete_removes_server_and_secrets() {
        let d = tempfile::tempdir().unwrap();
        let m = MemoryStore::default();
        save_server(d.path(), &m, stdio("shop"), &sec("TOKEN", "v1")).unwrap();
        delete(d.path(), &m, "shop").unwrap();
        assert!(load(d.path()).is_empty());
        assert_eq!(m.get("mcp:shop:TOKEN"), None);
    }

    #[test]
    fn load_missing_or_corrupt_is_empty() {
        let d = tempfile::tempdir().unwrap();
        assert!(load(d.path()).is_empty());
        std::fs::write(d.path().join("mcp.json"), "{oops").unwrap();
        assert!(load(d.path()).is_empty());
    }
}
