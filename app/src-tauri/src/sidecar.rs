use std::collections::HashMap;
use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
#[cfg(unix)]
use std::time::{Duration, Instant};

use crate::settings::Settings;
use crate::secrets::{SecretStore, API_KEY_ACCOUNT, ELEVEN_ACCOUNT, OAUTH_ACCOUNT, SOCIAL_ACCOUNT};

#[derive(Debug, Clone, PartialEq)]
pub struct EngineCmd {
    pub program: PathBuf,
    pub prefix_args: Vec<String>,
    pub bin_dir: Option<PathBuf>,
}

fn exe(name: &str) -> String {
    if cfg!(windows) { format!("{name}.exe") } else { name.to_string() }
}

pub fn locate_engine(resource_dir: Option<&Path>, repo_root: Option<&Path>) -> Option<EngineCmd> {
    if let Some(p) = std::env::var_os("AUTOEDIT_ENGINE").map(PathBuf::from).filter(|p| p.is_file()) {
        return Some(EngineCmd { program: p, prefix_args: vec![], bin_dir: None });
    }
    if let Some(res) = resource_dir {
        let p = res.join("engine").join(exe("autoedit"));
        if p.is_file() {
            let bin = res.join("bin");
            return Some(EngineCmd { program: p, prefix_args: vec![], bin_dir: bin.is_dir().then_some(bin) });
        }
    }
    let root = repo_root?;
    let built = root.join("engine").join("dist").join("autoedit").join(exe("autoedit"));
    if built.is_file() {
        return Some(EngineCmd { program: built, prefix_args: vec![], bin_dir: None });
    }
    let dir = root.join("engine");
    if !dir.is_dir() {
        return None;
    }
    Some(EngineCmd {
        program: PathBuf::from("uv"),
        prefix_args: ["run", "--directory", &dir.to_string_lossy(), "autoedit"].map(String::from).to_vec(),
        bin_dir: None,
    })
}

pub fn engine_env(
    secrets: &dyn SecretStore,
    model: &str,
    has_claude_code: bool,
    settings: &Settings,
    mcp_json: &str,
    args: &[String],
) -> Vec<(String, String)> {
    let sub = args.first().map(String::as_str).unwrap_or("");
    let is_social = sub == "social";
    let wants_mcp = sub == "edit" || sub == "mcp-check";
    let mut env = vec![
        ("DISABLE_AUTOUPDATER".to_string(), "1".to_string()),
        ("AUTOEDIT_CLAUDE_MODEL".to_string(), model.to_string()),
        ("PYTHONUNBUFFERED".to_string(), "1".to_string()),
        ("PYTHONIOENCODING".to_string(), "utf-8".to_string()),
    ];
    if let Some(tok) = secrets.get(OAUTH_ACCOUNT) {
        env.push(("CLAUDE_CODE_OAUTH_TOKEN".into(), tok));
    } else if !has_claude_code && let Some(key) = secrets.get(API_KEY_ACCOUNT) {
        env.push(("ANTHROPIC_API_KEY".into(), key));
    }
    // Least privilege: each secret only reaches the commands that need it.
    if is_social {
        if let Some(k) = secrets.get(SOCIAL_ACCOUNT) {
            env.push(("BUNDLE_SOCIAL_KEY".into(), k));
        }
        env.push((
            "AUTOEDIT_ROUTINES".into(),
            serde_json::to_string(&settings.routines).unwrap_or_else(|_| "[]".into()),
        ));
        env.push(("AUTOEDIT_PROJECTS_ROOT".into(), settings.projects_root.clone()));
    }
    if wants_mcp {
        env.push(("AUTOEDIT_MCP".into(), mcp_json.to_string()));
    }
    // Voiceover runs only inside an edit.
    if sub == "edit"
        && let Some(k) = secrets.get(ELEVEN_ACCOUNT)
    {
        env.push(("ELEVENLABS_API_KEY".into(), k));
    }
    if !cfg!(windows)
        && let Some(home) = std::env::var_os("HOME").map(PathBuf::from)
    {
        let inherited = std::env::var("PATH").unwrap_or_default();
        env.push(("PATH".into(), augmented_path(&home, &inherited)));
    }
    env
}

/// A GUI app starts with a minimal PATH. Prepend the usual user tool dirs that exist
/// (node, npx, uvx, bun, cargo ...) so customer MCP servers can be found.
pub fn augmented_path(home: &Path, inherited: &str) -> String {
    let mut dirs: Vec<PathBuf> = ["/opt/homebrew/bin", "/usr/local/bin"].iter().map(PathBuf::from).collect();
    for rel in [".volta/bin", ".local/bin", ".bun/bin", ".cargo/bin"] {
        dirs.push(home.join(rel));
    }
    let nvm = home.join(".nvm").join("versions").join("node");
    let newest = std::fs::read_dir(&nvm)
        .into_iter()
        .flatten()
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.join("bin").is_dir())
        .max_by_key(|p| node_version(p));
    if let Some(n) = newest {
        dirs.push(n.join("bin"));
    }
    let mut out: Vec<String> = Vec::new();
    for d in dirs.into_iter().filter(|d| d.is_dir()) {
        let s = d.to_string_lossy().into_owned();
        if !out.contains(&s) {
            out.push(s);
        }
    }
    for part in inherited.split(':').filter(|p| !p.is_empty()) {
        if !out.iter().any(|x| x == part) {
            out.push(part.to_string());
        }
    }
    out.join(":")
}

fn node_version(p: &Path) -> Vec<u64> {
    p.file_name()
        .map(|n| n.to_string_lossy().trim_start_matches('v').split('.').map(|x| x.parse().unwrap_or(0)).collect())
        .unwrap_or_default()
}

#[derive(Default)]
/// job id -> (pid, the `--project` dir it works on).
pub struct Jobs(Mutex<HashMap<String, (u32, Option<String>)>>);

/// The value after `--project` in an engine command line.
fn project_arg(args: &[String]) -> Option<String> {
    args.iter().position(|a| a == "--project").and_then(|i| args.get(i + 1)).cloned()
}

fn same_dir(a: &str, b: &Path) -> bool {
    let a = Path::new(a);
    match (a.canonicalize(), b.canonicalize()) {
        (Ok(x), Ok(y)) => x == y,
        _ => a == b,
    }
}

impl Jobs {
    fn insert(&self, id: &str, pid: u32, project: Option<String>) {
        self.0.lock().unwrap().insert(id.into(), (pid, project));
    }
    /// An engine job (edit, chat, analyze, publish...) is running on this project.
    pub fn busy_on(&self, dir: &Path) -> bool {
        self.0.lock().unwrap().values().any(|(_, p)| p.as_deref().is_some_and(|p| same_dir(p, dir)))
    }
    fn remove(&self, id: &str) {
        self.0.lock().unwrap().remove(id);
    }
    fn pid(&self, id: &str) -> Option<u32> {
        self.0.lock().unwrap().get(id).map(|(pid, _)| *pid)
    }
    fn all(&self) -> Vec<(String, u32)> {
        self.0.lock().unwrap().iter().map(|(k, (pid, _))| (k.clone(), *pid)).collect()
    }
}

/// Read one line at a time, replacing invalid UTF-8 instead of ending the loop
/// (an undrained pipe would block the engine once its buffer fills).
fn lossy_lines<R: BufRead>(mut r: R) -> impl Iterator<Item = String> {
    std::iter::from_fn(move || {
        let mut buf = Vec::new();
        match r.read_until(b'\n', &mut buf) {
            Ok(0) | Err(_) => None,
            Ok(_) => {
                let line = String::from_utf8_lossy(&buf);
                Some(line.trim_end_matches(['\n', '\r']).to_string())
            }
        }
    })
}

#[derive(Debug)]
pub enum JobMsg {
    Event { job: String, event: serde_json::Value },
    Exit { job: String, code: Option<i32> },
}

fn append_log(path: &Path) -> Option<std::fs::File> {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    OpenOptions::new().create(true).append(true).open(path).ok()
}

/// Spawn the engine. Every `Event` is delivered before the final `Exit`.
pub fn spawn_job<F>(
    cmd: &EngineCmd,
    args: &[String],
    env: &[(String, String)],
    log_file: &Path,
    jobs: Arc<Jobs>,
    on: F,
) -> std::io::Result<String>
where
    F: Fn(JobMsg) + Send + 'static,
{
    let mut c = Command::new(&cmd.program);
    c.args(&cmd.prefix_args).args(args);
    for (k, v) in env {
        c.env(k, v);
    }
    if let Some(b) = &cmd.bin_dir {
        c.env("AUTOEDIT_BIN_DIR", b);
    }
    // Python on Windows defaults to cp1252 for pipes and files; Vietnamese text needs UTF-8.
    c.env("PYTHONUTF8", "1").env("PYTHONIOENCODING", "utf-8");
    c.stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        c.process_group(0);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        c.creation_flags(0x0800_0000);
    }
    let mut child = c.spawn()?;
    let id = uuid::Uuid::new_v4().to_string();
    jobs.insert(&id, child.id(), project_arg(args));

    let stdout = child.stdout.take().expect("piped stdout");
    let stderr = child.stderr.take().expect("piped stderr");

    let job = id.clone();
    let out_log = append_log(log_file);
    let out_thread = std::thread::spawn(move || {
        let mut log = out_log;
        for line in lossy_lines(BufReader::new(stdout)) {
            match serde_json::from_str::<serde_json::Value>(&line) {
                Ok(v) if v.is_object() && v.get("type").is_some() => {
                    on(JobMsg::Event { job: job.clone(), event: v });
                }
                _ => {
                    if let Some(f) = log.as_mut() {
                        let _ = writeln!(f, "{line}");
                    }
                }
            }
        }
        on
    });

    let err_log = append_log(log_file);
    let err_thread = std::thread::spawn(move || {
        let mut log = err_log;
        for line in lossy_lines(BufReader::new(stderr)) {
            if let Some(f) = log.as_mut() {
                let _ = writeln!(f, "{line}");
            }
        }
    });

    let job = id.clone();
    std::thread::spawn(move || {
        let on = out_thread.join().ok();
        let status = child.wait();
        let _ = err_thread.join();
        jobs.remove(&job);
        if let Some(on) = on {
            on(JobMsg::Exit { job, code: status.ok().and_then(|s| s.code()) });
        }
    });
    Ok(id)
}

/// Stop a job and its children: polite first, forceful after 2 seconds.
pub fn cancel(jobs: &Jobs, job: &str) {
    let Some(pid) = jobs.pid(job) else { return };
    #[cfg(unix)]
    {
        // SAFETY: plain signal to the process group we created with process_group(0).
        unsafe { libc::killpg(pid as i32, libc::SIGTERM) };
        let until = Instant::now() + Duration::from_secs(2);
        while Instant::now() < until {
            if jobs.pid(job).is_none() {
                return;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        if jobs.pid(job).is_some() {
            unsafe { libc::killpg(pid as i32, libc::SIGKILL) };
        }
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let _ = Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(0x0800_0000)
            .status();
    }
}

/// Stop every running job (app exit, updater relaunch). Parallel: TERM all, then KILL stragglers.
pub fn kill_all(jobs: &Jobs) {
    let all = jobs.all();
    if all.is_empty() {
        return;
    }
    #[cfg(unix)]
    {
        for (_, pid) in &all {
            // SAFETY: signal to the process group we created with process_group(0).
            unsafe { libc::killpg(*pid as i32, libc::SIGTERM) };
        }
        let until = Instant::now() + Duration::from_secs(2);
        while Instant::now() < until && all.iter().any(|(id, _)| jobs.pid(id).is_some()) {
            std::thread::sleep(Duration::from_millis(50));
        }
        for (id, pid) in &all {
            if jobs.pid(id).is_some() {
                unsafe { libc::killpg(*pid as i32, libc::SIGKILL) };
            }
        }
    }
    #[cfg(windows)]
    for (id, _) in &all {
        cancel(jobs, id);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn busy_on_matches_the_project_arg() {
        let d = tempfile::tempdir().unwrap();
        let a = d.path().join("2026-11-20_a");
        let b = d.path().join("2026-11-20_b");
        std::fs::create_dir_all(&a).unwrap();
        std::fs::create_dir_all(&b).unwrap();
        let args = |p: &Path| vec!["chat".to_string(), "--project".into(), p.to_string_lossy().into_owned()];
        assert_eq!(project_arg(&args(&a)), Some(a.to_string_lossy().into_owned()));
        assert_eq!(project_arg(&["setup".to_string()]), None);
        let jobs = Jobs::default();
        jobs.insert("j1", 1, project_arg(&args(&a)));
        jobs.insert("j2", 2, None);
        assert!(jobs.busy_on(&a));
        assert!(jobs.busy_on(&b.join("..").join("2026-11-20_a")));
        assert!(!jobs.busy_on(&b));
        jobs.remove("j1");
        assert!(!jobs.busy_on(&a));
    }
    use crate::secrets::MemoryStore;

    fn fake() -> EngineCmd {
        EngineCmd {
            program: PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/fixtures/fake-engine.sh")),
            prefix_args: vec![],
            bin_dir: None,
        }
    }
    #[test]
    fn env_prefers_app_token_and_never_both() {
        let m = MemoryStore::default();
        m.set(OAUTH_ACCOUNT, "tok").unwrap();
        m.set(API_KEY_ACCOUNT, "key").unwrap();
        let e = engine_env(&m, "claude-opus-5-5", false, &Settings::default(), "{}", &[]);
        assert!(e.contains(&("CLAUDE_CODE_OAUTH_TOKEN".into(), "tok".into())));
        assert!(!e.iter().any(|(k, _)| k == "ANTHROPIC_API_KEY"));
        assert!(e.contains(&("DISABLE_AUTOUPDATER".into(), "1".into())));
    }
    #[test]
    fn env_api_key_only_without_any_subscription() {
        let m = MemoryStore::default();
        m.set(API_KEY_ACCOUNT, "key").unwrap();
        assert!(engine_env(&m, "m", false, &Settings::default(), "{}", &[]).iter().any(|(k, _)| k == "ANTHROPIC_API_KEY"));
        assert!(!engine_env(&m, "m", true, &Settings::default(), "{}", &[]).iter().any(|(k, _)| k == "ANTHROPIC_API_KEY"));
    }
    #[test]
    fn env_eleven_key_only_for_edit() {
        let m = MemoryStore::default();
        m.set(ELEVEN_ACCOUNT, "test-key").unwrap();
        let run = |sub: &str| engine_env(&m, "m", false, &Settings::default(), "{}", &[sub.to_string(), "/p".into()]);
        assert!(run("edit").contains(&("ELEVENLABS_API_KEY".into(), "test-key".into())));
        for sub in ["social", "analyze", "mcp-check", "auth-check", "setup"] {
            assert!(!run(sub).iter().any(|(k, _)| k == "ELEVENLABS_API_KEY"), "{sub}");
        }
        assert!(!engine_env(&m, "m", false, &Settings::default(), "{}", &[]).iter().any(|(k, _)| k == "ELEVENLABS_API_KEY"));
        let empty = MemoryStore::default();
        let e = engine_env(&empty, "m", false, &Settings::default(), "{}", &["edit".into()]);
        assert!(!e.iter().any(|(k, _)| k == "ELEVENLABS_API_KEY"));
    }
    #[test]
    fn env_social_key_routines_projects_root_and_mcp() {
        use crate::settings::Routine;
        let m = MemoryStore::default();
        let st = Settings {
            projects_root: "/p".into(),
            routines: vec![Routine { id: "r".into(), time: "19:30".into(), channels: vec!["TIKTOK".into()], enabled: true }],
            ..Default::default()
        };
        let social: Vec<String> = vec!["social".into(), "check".into()];
        let none = engine_env(&m, "m", false, &st, "{}", &social);
        assert!(!none.iter().any(|(k, _)| k == "BUNDLE_SOCIAL_KEY"));
        m.set(SOCIAL_ACCOUNT, "bk").unwrap();
        let e = engine_env(&m, "m", false, &st, r#"{"x":{}}"#, &social);
        assert!(e.contains(&("BUNDLE_SOCIAL_KEY".into(), "bk".into())));
        let get = |k: &str| e.iter().find(|(n, _)| n == k).unwrap().1.clone();
        let routines: serde_json::Value = serde_json::from_str(&get("AUTOEDIT_ROUTINES")).unwrap();
        assert_eq!(routines[0]["time"], "19:30");
        assert_eq!(get("AUTOEDIT_PROJECTS_ROOT"), "/p");
        assert!(!e.iter().any(|(k, _)| k == "AUTOEDIT_MCP"));
        let edit: Vec<String> = vec!["edit".into()];
        let e = engine_env(&m, "m", false, &st, r#"{"x":{}}"#, &edit);
        let get = |k: &str| e.iter().find(|(n, _)| n == k).unwrap().1.clone();
        assert_eq!(get("AUTOEDIT_MCP"), r#"{"x":{}}"#);
        assert!(!e.iter().any(|(k, _)| k == "BUNDLE_SOCIAL_KEY" || k == "AUTOEDIT_ROUTINES"));
        let chk: Vec<String> = vec!["mcp-check".into(), "--name".into(), "x".into()];
        assert!(engine_env(&m, "m", false, &st, "{}", &chk).iter().any(|(k, _)| k == "AUTOEDIT_MCP"));
        for a in [vec!["analyze"], vec!["setup"], vec![]] {
            let a: Vec<String> = a.into_iter().map(String::from).collect();
            let e = engine_env(&m, "m", false, &st, "{}", &a);
            assert!(!e.iter().any(|(k, _)| k == "BUNDLE_SOCIAL_KEY" || k == "AUTOEDIT_MCP"));
        }
    }
    #[test]
    fn augmented_path_prepends_existing_dirs_only() {
        let h = tempfile::tempdir().unwrap();
        for d in [".volta/bin", ".cargo/bin", ".nvm/versions/node/v18.2.0/bin", ".nvm/versions/node/v20.10.0/bin", ".nvm/versions/node/v9.0.0/bin"] {
            std::fs::create_dir_all(h.path().join(d)).unwrap();
        }
        let p = augmented_path(h.path(), "/usr/bin:/bin");
        let parts: Vec<&str> = p.split(':').collect();
        let hs = h.path().to_string_lossy();
        assert!(parts.contains(&format!("{hs}/.volta/bin").as_str()));
        assert!(parts.contains(&format!("{hs}/.cargo/bin").as_str()));
        assert!(!parts.contains(&format!("{hs}/.bun/bin").as_str()));
        assert!(parts.contains(&format!("{hs}/.nvm/versions/node/v20.10.0/bin").as_str()));
        assert!(!p.contains("v18.2.0") && !p.contains("v9.0.0"));
        assert!(p.ends_with(":/usr/bin:/bin"));
        let idx = |x: &str| parts.iter().position(|y| *y == x).unwrap();
        assert!(idx(&format!("{hs}/.volta/bin")) < idx("/usr/bin"));
    }
    #[test]
    fn locate_packaged_engine_with_bin_dir() {
        let d = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(d.path().join("engine")).unwrap();
        std::fs::create_dir_all(d.path().join("bin")).unwrap();
        std::fs::write(d.path().join("engine").join(exe("autoedit")), b"x").unwrap();
        let c = locate_engine(Some(d.path()), None).unwrap();
        assert_eq!(c.program, d.path().join("engine").join(exe("autoedit")));
        assert_eq!(c.bin_dir, Some(d.path().join("bin")));
    }
    #[test]
    fn locate_dev_falls_back_to_uv_and_none_when_absent() {
        let d = tempfile::tempdir().unwrap();
        assert!(locate_engine(None, Some(d.path())).is_none());
        std::fs::create_dir_all(d.path().join("engine")).unwrap();
        let c = locate_engine(None, Some(d.path())).unwrap();
        assert_eq!(c.program, PathBuf::from("uv"));
        assert_eq!(c.prefix_args[0], "run");
        assert_eq!(c.prefix_args.last().unwrap(), "autoedit");
    }
    #[cfg(unix)]
    #[test]
    fn spawn_streams_json_events_and_exit() {
        let d = tempfile::tempdir().unwrap();
        let (tx, rx) = std::sync::mpsc::channel();
        let jobs = Arc::new(Jobs::default());
        spawn_job(
            &fake(),
            &[],
            &[("CLAUDE_CODE_OAUTH_TOKEN".into(), "secret".into())],
            &d.path().join("engine.log"),
            jobs,
            move |m| {
                tx.send(m).unwrap();
            },
        )
        .unwrap();
        let msgs: Vec<JobMsg> = rx.iter().take(3).collect();
        assert!(matches!(&msgs[0], JobMsg::Event { event, .. } if event["type"] == "step"));
        assert!(matches!(&msgs[1], JobMsg::Event { event, .. } if event["type"] == "done"));
        assert!(matches!(&msgs[2], JobMsg::Exit { code: Some(0), .. }));
        let log = std::fs::read_to_string(d.path().join("engine.log")).unwrap();
        assert!(log.contains("not json"));
    }
    #[cfg(unix)]
    #[test]
    fn cancel_kills_the_job() {
        let d = tempfile::tempdir().unwrap();
        let (tx, rx) = std::sync::mpsc::channel();
        let jobs = Arc::new(Jobs::default());
        let id = spawn_job(&fake(), &["sleep".into()], &[], &d.path().join("e.log"), jobs.clone(), move |m| {
            tx.send(m).unwrap();
        })
        .unwrap();
        std::thread::sleep(std::time::Duration::from_millis(300));
        cancel(&jobs, &id);
        let exit = rx.iter().find(|m| matches!(m, JobMsg::Exit { .. })).unwrap();
        assert!(matches!(exit, JobMsg::Exit { code, .. } if code != Some(0)));
    }
    #[cfg(unix)]
    #[test]
    fn kill_all_stops_every_running_job() {
        let d = tempfile::tempdir().unwrap();
        let (tx, rx) = std::sync::mpsc::channel();
        let jobs = Arc::new(Jobs::default());
        for _ in 0..2 {
            let tx = tx.clone();
            spawn_job(&fake(), &["sleep".into()], &[], &d.path().join("e.log"), jobs.clone(), move |m| {
                tx.send(m).unwrap();
            })
            .unwrap();
        }
        std::thread::sleep(std::time::Duration::from_millis(300));
        kill_all(&jobs);
        let exits = rx.iter().filter(|m| matches!(m, JobMsg::Exit { .. })).take(2).count();
        assert_eq!(exits, 2);
        assert!(jobs.all().is_empty());
    }
    #[test]
    fn lossy_lines_survive_invalid_utf8() {
        let data: &[u8] = b"one\n\xff\xfe bad\r\nthree";
        let lines: Vec<String> = lossy_lines(BufReader::new(data)).collect();
        assert_eq!(lines.len(), 3);
        assert_eq!(lines[0], "one");
        assert!(lines[1].contains("bad"));
        assert_eq!(lines[2], "three");
    }
}
