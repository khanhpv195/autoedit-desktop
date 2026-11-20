use std::io::{Read, Write};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, mpsc};
use std::time::Duration;

use portable_pty::{ChildKiller, CommandBuilder, MasterPty, PtySize, native_pty_system};
use regex::Regex;
use serde::Serialize;

use crate::secrets::{OAUTH_ACCOUNT, SecretStore};

const TIMEOUT: Duration = Duration::from_secs(600);
const REAL_TOKEN_MIN_LEN: usize = 100;

fn is_token_char(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '_' || c == '-'
}

/// Remove terminal escape sequences. Cursor-forward becomes a space so words stay apart.
pub fn strip_ansi(s: &str) -> String {
    let fwd = Regex::new(r"\x1b\[\d*C").unwrap();
    let any = Regex::new(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]").unwrap();
    any.replace_all(&fwd.replace_all(s, " "), "").into_owned()
}

pub fn redact(s: &str) -> String {
    Regex::new(r"sk-ant-[A-Za-z0-9_-]+").unwrap().replace_all(s, "[đã ẩn]").into_owned()
}

pub fn find_url(s: &str) -> Option<String> {
    Regex::new(r"https://\S+").unwrap().find(s).map(|m| m.as_str().to_string())
}

fn find_token(text: &str, require_terminator: bool) -> Option<String> {
    let re = Regex::new(r"sk-ant-oat01-[A-Za-z0-9_-]{20,}").unwrap();
    let clean = strip_ansi(text);
    let accept = |hay: &str, m: regex::Match<'_>| !require_terminator || hay[m.end()..].chars().next().is_some();
    // Real tokens are long and arrive on one line (the PTY is 1000 columns wide).
    if let Some(m) = re.find(&clean).filter(|m| m.as_str().len() >= REAL_TOKEN_MIN_LEN && accept(&clean, *m)) {
        return Some(m.as_str().to_string());
    }
    // Otherwise a hard wrap may have split the token: drop a line break between two token chars.
    let chars: Vec<char> = clean.chars().collect();
    let mut joined = String::with_capacity(clean.len());
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == '\r' || chars[i] == '\n' {
            let mut j = i;
            while j < chars.len() && (chars[j] == '\r' || chars[j] == '\n') {
                j += 1;
            }
            let single_break = chars[i..j].iter().filter(|c| **c == '\n').count() <= 1;
            if single_break && i > 0 && j < chars.len() && is_token_char(chars[i - 1]) && is_token_char(chars[j]) {
                i = j;
                continue;
            }
        }
        joined.push(chars[i]);
        i += 1;
    }
    re.find(&joined).filter(|m| accept(&joined, *m)).map(|m| m.as_str().to_string())
}

#[allow(dead_code)] // public API per plan; the live session uses find_token(require_terminator)
pub fn extract_token(text: &str) -> Option<String> {
    find_token(text, false)
}

#[derive(Debug, Clone, Serialize)]
pub struct LoginLine {
    pub line: String,
    pub url: Option<String>,
}

pub struct LoginSession {
    master: Mutex<Box<dyn MasterPty + Send>>,
    writer: Mutex<Box<dyn Write + Send>>,
    killer: Mutex<Box<dyn ChildKiller + Send + Sync>>,
    cancelled: Arc<AtomicBool>,
}

impl LoginSession {
    pub fn start(
        cli: &Path,
        secrets: Arc<dyn SecretStore + Send + Sync>,
        on_line: impl Fn(LoginLine) + Send + 'static,
        on_done: impl FnOnce(Result<(), String>) + Send + 'static,
    ) -> Result<LoginSession, String> {
        let pair = native_pty_system()
            .openpty(PtySize { rows: 40, cols: 1000, pixel_width: 0, pixel_height: 0 })
            .map_err(|e| e.to_string())?;
        let mut cmd = CommandBuilder::new(cli);
        cmd.arg("setup-token");
        cmd.env("DISABLE_AUTOUPDATER", "1");
        cmd.env_remove("CLAUDE_CODE_OAUTH_TOKEN");
        cmd.env_remove("ANTHROPIC_API_KEY");
        let mut child = pair.slave.spawn_command(cmd).map_err(|e| format!("Không chạy được Claude: {e}"))?;
        drop(pair.slave); // so the reader sees EOF when the child exits
        let mut reader = pair.master.try_clone_reader().map_err(|e| e.to_string())?;
        let writer = pair.master.take_writer().map_err(|e| e.to_string())?;
        let killer = child.clone_killer();
        let cancelled = Arc::new(AtomicBool::new(false));
        let timed_out = Arc::new(AtomicBool::new(false));

        let (stop_tx, stop_rx) = mpsc::channel::<()>();
        {
            let mut k = child.clone_killer();
            let timed_out = timed_out.clone();
            std::thread::spawn(move || {
                if stop_rx.recv_timeout(TIMEOUT) == Err(mpsc::RecvTimeoutError::Timeout) {
                    timed_out.store(true, Ordering::SeqCst);
                    let _ = k.kill();
                }
            });
        }

        let cancelled_r = cancelled.clone();
        let mut kill_on_token = child.clone_killer();
        std::thread::spawn(move || {
            let mut raw: Vec<u8> = Vec::new();
            let mut pending = String::new();
            let mut buf = [0u8; 4096];
            let mut token: Option<String> = None;
            while let Ok(n) = reader.read(&mut buf) {
                if n == 0 {
                    break;
                }
                raw.extend_from_slice(&buf[..n]);
                pending.push_str(&String::from_utf8_lossy(&buf[..n]));
                while let Some(pos) = pending.find(['\n', '\r']) {
                    let raw_line: String = pending.drain(..=pos).collect();
                    let line = redact(strip_ansi(&raw_line).trim());
                    if line.chars().count() > 1 {
                        let url = find_url(&line);
                        on_line(LoginLine { line, url });
                    }
                }
                if let Some(t) = find_token(&String::from_utf8_lossy(&raw), true) {
                    token = Some(t);
                    break;
                }
            }
            let _ = stop_tx.send(());
            let result = match token {
                Some(t) => match secrets.set(OAUTH_ACCOUNT, &t) {
                    Ok(()) => {
                        let _ = kill_on_token.kill();
                        Ok(())
                    }
                    Err(e) => Err(format!("Không lưu được mã đăng nhập: {e}")),
                },
                None if cancelled_r.load(Ordering::SeqCst) => Err("Đã hủy đăng nhập".to_string()),
                None if timed_out.load(Ordering::SeqCst) => Err("Hết thời gian chờ đăng nhập".to_string()),
                None => Err("Không lấy được mã đăng nhập".to_string()),
            };
            let _ = child.wait();
            on_done(result);
        });

        Ok(LoginSession {
            master: Mutex::new(pair.master),
            writer: Mutex::new(writer),
            killer: Mutex::new(killer),
            cancelled,
        })
    }

    pub fn write_input(&self, text: &str) -> Result<(), String> {
        let _keep_master_alive = self.master.lock().map_err(|e| e.to_string())?;
        let mut w = self.writer.lock().map_err(|e| e.to_string())?;
        w.write_all(format!("{text}\r").as_bytes()).map_err(|e| e.to_string())?;
        w.flush().map_err(|e| e.to_string())
    }

    pub fn cancel(&self) {
        self.cancelled.store(true, Ordering::SeqCst);
        if let Ok(mut k) = self.killer.lock() {
            let _ = k.kill();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::secrets::MemoryStore;
    use std::path::PathBuf;

    #[test]
    fn extract_token_through_ansi_and_wrap() {
        let raw = "x \u{1b}[32msk-ant-oat01-AbCdEfGhIj\r\nKlMnOpQrStUvWxYz_01\u{1b}[0m\n";
        assert_eq!(extract_token(raw).as_deref(), Some("sk-ant-oat01-AbCdEfGhIjKlMnOpQrStUvWxYz_01"));
        assert_eq!(extract_token("nothing here"), None);
    }
    #[test]
    fn redact_hides_tokens() {
        assert_eq!(redact("tok sk-ant-oat01-abcDEF_12-3 ok"), "tok [đã ẩn] ok");
    }
    #[test]
    fn strip_ansi_keeps_words_apart_and_url_whole() {
        assert_eq!(strip_ansi("Paste\u{1b}[1Ccode\u{1b}[2Chere"), "Paste code here");
        let u = find_url(&strip_ansi("\u{1b}[1mgo\u{1b}[0m https://claude.com/cai/oauth/authorize?a=1&b=2")).unwrap();
        assert_eq!(u, "https://claude.com/cai/oauth/authorize?a=1&b=2");
    }
    #[test]
    fn long_token_followed_by_text_is_not_swallowed() {
        let tok = format!("sk-ant-oat01-{}", "A".repeat(95));
        let raw = format!("{tok}\nStore this token securely.\n");
        assert_eq!(extract_token(&raw).as_deref(), Some(tok.as_str()));
    }
    #[test]
    fn partial_token_without_terminator_is_not_accepted_live() {
        assert_eq!(find_token("sk-ant-oat01-AbCdEfGhIjKlMnOpQrStUvWx", true), None);
    }
    #[cfg(unix)]
    #[test]
    fn login_session_with_fake_cli_stores_token_and_never_leaks_it() {
        let store = Arc::new(MemoryStore::default());
        let (tx, rx) = std::sync::mpsc::channel::<String>();
        let (dtx, drx) = std::sync::mpsc::channel();
        let cli = PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/fixtures/fake-claude.sh"));
        let s = LoginSession::start(
            &cli,
            store.clone(),
            move |l| {
                tx.send(l.line).unwrap();
            },
            move |r| {
                dtx.send(r).unwrap();
            },
        )
        .unwrap();
        std::thread::sleep(Duration::from_millis(500));
        s.write_input("CODE123").unwrap();
        assert!(drx.recv_timeout(Duration::from_secs(10)).unwrap().is_ok());
        assert!(store.get(OAUTH_ACCOUNT).unwrap().starts_with("sk-ant-oat01-AbCd"));
        let lines: Vec<String> = rx.try_iter().collect();
        assert!(lines.iter().any(|l| l.contains("https://claude.ai/oauth/authorize")));
        assert!(lines.iter().all(|l| !l.contains("sk-ant-oat01")));
    }
    #[cfg(unix)]
    #[test]
    fn cancel_reports_error_and_stores_nothing() {
        let store = Arc::new(MemoryStore::default());
        let (dtx, drx) = std::sync::mpsc::channel();
        let cli = PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/fixtures/fake-claude.sh"));
        let s = LoginSession::start(&cli, store.clone(), |_| {}, move |r| {
            dtx.send(r).unwrap();
        })
        .unwrap();
        std::thread::sleep(Duration::from_millis(300));
        s.cancel();
        assert!(drx.recv_timeout(Duration::from_secs(10)).unwrap().is_err());
        assert_eq!(store.get(OAUTH_ACCOUNT), None);
    }
}
