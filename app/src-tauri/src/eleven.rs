//! ElevenLabs key check and voice list (spec 2026-11-21 voiceover A1). The key is read from the
//! Keychain, sent only as the `xi-api-key` header, and never returned to the UI or logged.
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;

use crate::secrets::{SecretStore, ELEVEN_ACCOUNT};
use crate::settings;

pub const BASE: &str = "https://api.elevenlabs.io";
const USER_AGENT: &str = concat!("AutoEdit/", env!("CARGO_PKG_VERSION"));

type Store = dyn SecretStore + Send + Sync;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ElevenErr {
    /// 401 from ElevenLabs, or no key stored.
    KeyInvalid,
    /// Network error, timeout, or an answer that is not ElevenLabs JSON.
    Offline,
    /// ElevenLabs answered with an error status other than 401 (429 busy, 5xx, ...).
    Failed,
    /// The key was valid but the Keychain refused to store it.
    Store,
}

impl ElevenErr {
    pub fn code(&self) -> &'static str {
        match self {
            ElevenErr::KeyInvalid => "ELEVEN_KEY_INVALID",
            ElevenErr::Offline => "ELEVEN_OFFLINE",
            ElevenErr::Failed => "ELEVEN_FAILED",
            ElevenErr::Store => "Không lưu được key vào Keychain",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Voice {
    pub id: String,
    pub name: String,
    pub labels: HashMap<String, String>,
    pub preview_url: Option<String>,
}

#[derive(Deserialize)]
struct RawVoice {
    voice_id: String,
    #[serde(default)]
    name: String,
    #[serde(default)]
    labels: Option<HashMap<String, serde_json::Value>>,
    #[serde(default)]
    preview_url: Option<String>,
}

async fn get(base: &str, path: &str, key: &str) -> Result<serde_json::Value, ElevenErr> {
    let client = reqwest::Client::builder()
        .user_agent(USER_AGENT)
        .timeout(std::time::Duration::from_secs(20))
        .build()
        .map_err(|_| ElevenErr::Offline)?;
    // Errors are mapped to codes only: nothing that could carry the key is logged or returned.
    let r = client.get(format!("{base}{path}")).header("xi-api-key", key).send().await.map_err(|_| ElevenErr::Offline)?;
    match r.status().as_u16() {
        200 => r.json::<serde_json::Value>().await.map_err(|_| ElevenErr::Offline),
        401 => Err(ElevenErr::KeyInvalid),
        _ => Err(ElevenErr::Failed),
    }
}

/// Remaining characters this billing period (`character_limit - character_count`).
pub async fn subscription(base: &str, key: &str) -> Result<u64, ElevenErr> {
    let v = get(base, "/v1/user/subscription", key).await?;
    let limit = v["character_limit"].as_u64().ok_or(ElevenErr::Offline)?;
    let used = v["character_count"].as_u64().unwrap_or(0);
    Ok(limit.saturating_sub(used))
}

pub async fn voices(base: &str, key: &str) -> Result<Vec<Voice>, ElevenErr> {
    let v = get(base, "/v1/voices", key).await?;
    let raw: Vec<RawVoice> = serde_json::from_value(v["voices"].clone()).map_err(|_| ElevenErr::Offline)?;
    Ok(raw
        .into_iter()
        .map(|r| Voice {
            id: r.voice_id,
            name: r.name,
            labels: r
                .labels
                .unwrap_or_default()
                .into_iter()
                .filter_map(|(k, v)| v.as_str().map(|s| (k, s.to_string())))
                .collect(),
            preview_url: r.preview_url.filter(|u| !u.is_empty()),
        })
        .collect())
}

/// `{hasKey, remaining?}`; `remaining` is left out when ElevenLabs cannot be asked right now.
pub async fn status(store: &Store, base: &str) -> serde_json::Value {
    let Some(key) = store.get(ELEVEN_ACCOUNT) else { return serde_json::json!({ "hasKey": false }) };
    match subscription(base, &key).await {
        Ok(n) => serde_json::json!({ "hasKey": true, "remaining": n }),
        Err(_) => serde_json::json!({ "hasKey": true }),
    }
}

/// Validate the key against ElevenLabs, then store it. Returns the remaining characters.
pub async fn set_key(store: &Store, base: &str, key: &str) -> Result<u64, ElevenErr> {
    let key = key.trim();
    if key.is_empty() {
        return Err(ElevenErr::KeyInvalid);
    }
    let remaining = subscription(base, key).await?;
    store.set(ELEVEN_ACCOUNT, key).map_err(|_| ElevenErr::Store)?;
    Ok(remaining)
}

pub async fn voices_for(store: &Store, base: &str) -> Result<Vec<Voice>, ElevenErr> {
    let key = store.get(ELEVEN_ACCOUNT).ok_or(ElevenErr::KeyInvalid)?;
    voices(base, &key).await
}

/// Remove the key and the default voice that belonged to that account.
pub fn clear_key(store: &Store, data_dir: &Path) -> Result<(), String> {
    store.delete(ELEVEN_ACCOUNT)?;
    let mut s = settings::load(data_dir);
    if s.voice_id.is_some() || s.voice_name.is_some() {
        s.voice_id = None;
        s.voice_name = None;
        settings::save(data_dir, &s).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::secrets::{MemoryStore, SecretStore, ELEVEN_ACCOUNT};
    use std::io::{Read, Write};
    use std::sync::{Arc, Mutex};

    /// One-shot local HTTP server: answers the first request with `status`/`body` and records the request.
    fn serve(status: u16, body: &'static str) -> (String, Arc<Mutex<String>>) {
        let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let base = format!("http://{}", l.local_addr().unwrap());
        let seen = Arc::new(Mutex::new(String::new()));
        let rec = seen.clone();
        std::thread::spawn(move || {
            let (mut s, _) = l.accept().unwrap();
            let mut buf = Vec::new();
            let mut chunk = [0u8; 1024];
            while !buf.windows(4).any(|w| w == b"\r\n\r\n") {
                let n = s.read(&mut chunk).unwrap();
                if n == 0 {
                    break;
                }
                buf.extend_from_slice(&chunk[..n]);
            }
            *rec.lock().unwrap() = String::from_utf8_lossy(&buf).into_owned();
            let resp = format!(
                "HTTP/1.1 {status} X\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                body.len()
            );
            let _ = s.write_all(resp.as_bytes());
        });
        (base, seen)
    }

    const SUB: &str = r#"{"tier":"starter","character_count":1200,"character_limit":30000}"#;
    const VOICES: &str = r#"{"voices":[
        {"voice_id":"v1","name":"Lan","labels":{"gender":"female","accent":"northern"},"preview_url":"https://storage.googleapis.com/x/v1.mp3"},
        {"voice_id":"v2","name":"Minh","labels":null,"preview_url":null}
    ]}"#;

    #[tokio::test]
    async fn subscription_200_gives_remaining_and_sends_the_key_header() {
        let (base, seen) = serve(200, SUB);
        assert_eq!(subscription(&base, "test-key").await, Ok(28800));
        let req = seen.lock().unwrap().to_lowercase();
        assert!(req.starts_with("get /v1/user/subscription "), "{req}");
        assert!(req.contains("xi-api-key: test-key"));
    }

    #[tokio::test]
    async fn subscription_401_is_key_invalid_and_refused_is_offline() {
        let (base, _) = serve(401, r#"{"detail":{"status":"invalid_api_key"}}"#);
        assert_eq!(subscription(&base, "test-key").await, Err(ElevenErr::KeyInvalid));
        assert_eq!(subscription("http://127.0.0.1:9", "test-key").await, Err(ElevenErr::Offline));
        let (base, _) = serve(200, "<html>portal</html>");
        assert_eq!(subscription(&base, "test-key").await, Err(ElevenErr::Offline));
        assert_eq!(ElevenErr::KeyInvalid.code(), "ELEVEN_KEY_INVALID");
        assert_eq!(ElevenErr::Offline.code(), "ELEVEN_OFFLINE");
    }

    #[tokio::test]
    async fn http_429_and_5xx_are_failed_not_offline() {
        let (base, _) = serve(429, r#"{"detail":{"status":"too_many_concurrent_requests"}}"#);
        assert_eq!(subscription(&base, "test-key").await, Err(ElevenErr::Failed));
        let (base, _) = serve(500, "{}");
        assert_eq!(subscription(&base, "test-key").await, Err(ElevenErr::Failed));
        let (base, _) = serve(503, "{}");
        assert_eq!(voices(&base, "test-key").await.unwrap_err(), ElevenErr::Failed);
        let (base, _) = serve(429, "{}");
        let store = MemoryStore::default();
        assert_eq!(set_key(&store, &base, "test-key").await, Err(ElevenErr::Failed));
        assert_eq!(store.get(ELEVEN_ACCOUNT), None);
        assert_eq!(ElevenErr::Failed.code(), "ELEVEN_FAILED");
    }

    #[tokio::test]
    async fn voices_are_parsed() {
        let (base, seen) = serve(200, VOICES);
        let v = voices(&base, "test-key").await.unwrap();
        assert!(seen.lock().unwrap().starts_with("GET /v1/voices "));
        assert_eq!(v.len(), 2);
        assert_eq!(v[0].id, "v1");
        assert_eq!(v[0].name, "Lan");
        assert_eq!(v[0].labels.get("gender").map(String::as_str), Some("female"));
        assert_eq!(v[0].preview_url.as_deref(), Some("https://storage.googleapis.com/x/v1.mp3"));
        assert!(v[1].labels.is_empty() && v[1].preview_url.is_none());
        let json = serde_json::to_value(&v[0]).unwrap();
        assert_eq!(json["previewUrl"], "https://storage.googleapis.com/x/v1.mp3");
        assert_eq!(json["id"], "v1");
    }

    #[tokio::test]
    async fn set_key_stores_only_a_valid_key() {
        let store = MemoryStore::default();
        let (base, _) = serve(401, "{}");
        assert_eq!(set_key(&store, &base, "  bad-key ").await, Err(ElevenErr::KeyInvalid));
        assert_eq!(store.get(ELEVEN_ACCOUNT), None);
        assert_eq!(set_key(&store, "http://127.0.0.1:9", "test-key").await, Err(ElevenErr::Offline));
        assert_eq!(store.get(ELEVEN_ACCOUNT), None);
        let (base, seen) = serve(200, SUB);
        assert_eq!(set_key(&store, &base, " test-key\n").await, Ok(28800));
        assert_eq!(store.get(ELEVEN_ACCOUNT).as_deref(), Some("test-key"));
        assert!(seen.lock().unwrap().to_lowercase().contains("xi-api-key: test-key\r\n"));
    }

    #[tokio::test]
    async fn status_reports_key_and_remaining_without_the_key() {
        let store = MemoryStore::default();
        assert_eq!(status(&store, "http://127.0.0.1:9").await, serde_json::json!({ "hasKey": false }));
        store.set(ELEVEN_ACCOUNT, "test-key").unwrap();
        let (base, _) = serve(200, SUB);
        let s = status(&store, &base).await;
        assert_eq!(s, serde_json::json!({ "hasKey": true, "remaining": 28800 }));
        assert!(!s.to_string().contains("test-key"));
        // offline: still has a key, remaining unknown
        assert_eq!(status(&store, "http://127.0.0.1:9").await, serde_json::json!({ "hasKey": true }));
    }

    #[tokio::test]
    async fn voices_for_needs_a_key() {
        let store = MemoryStore::default();
        assert_eq!(voices_for(&store, "http://127.0.0.1:9").await.unwrap_err(), ElevenErr::KeyInvalid);
        store.set(ELEVEN_ACCOUNT, "test-key").unwrap();
        let (base, _) = serve(200, VOICES);
        assert_eq!(voices_for(&store, &base).await.unwrap().len(), 2);
    }

    #[test]
    fn clear_key_deletes_it_and_the_default_voice() {
        let d = tempfile::tempdir().unwrap();
        let store = MemoryStore::default();
        store.set(ELEVEN_ACCOUNT, "test-key").unwrap();
        let s = crate::settings::Settings {
            voice_id: Some("v1".into()),
            voice_name: Some("Lan".into()),
            onboarded: true,
            ..Default::default()
        };
        crate::settings::save(d.path(), &s).unwrap();
        clear_key(&store, d.path()).unwrap();
        assert_eq!(store.get(ELEVEN_ACCOUNT), None);
        let after = crate::settings::load(d.path());
        assert_eq!((after.voice_id, after.voice_name, after.onboarded), (None, None, true));
    }
}
