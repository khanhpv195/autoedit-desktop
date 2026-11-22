use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use tauri::{AppHandle, Emitter, Manager, State};

use crate::mcp::{self, McpServer};
use crate::secrets::{SecretStore, API_KEY_ACCOUNT, OAUTH_ACCOUNT, SOCIAL_ACCOUNT};
use crate::auth;
use crate::eleven;
use crate::login::{LoginLine, LoginSession};
use crate::projects::{self, FeedItem, ProjectDetail, ProjectSummary};
use crate::settings::{self, Settings};
use crate::sidecar::{self, JobMsg, Jobs};

pub type LoginSlot = Arc<Mutex<Option<(u64, Arc<LoginSession>)>>>;

pub struct AppState {
    pub secrets: Arc<dyn SecretStore + Send + Sync>,
    pub data_dir: PathBuf,
    pub jobs: Arc<Jobs>,
    pub login: LoginSlot,
    pub gate: Arc<crate::license::Gate>,
    /// Wakes the background license check (after a successful activation).
    pub license_wake: Arc<tokio::sync::Notify>,
}

static LOGIN_GEN: AtomicU64 = AtomicU64::new(1);

/// App is quitting or relaunching: stop every engine job and the login PTY.
pub fn shutdown(state: &AppState) {
    if let Some((_, s)) = state.login.lock().ok().and_then(|s| s.clone()) {
        s.cancel();
    }
    sidecar::kill_all(&state.jobs);
}

#[tauri::command(async)]
pub fn kill_all_jobs(state: State<'_, AppState>) {
    shutdown(&state);
}

#[tauri::command]
pub fn license_status(state: State<'_, AppState>) -> serde_json::Value {
    serde_json::json!({ "licensed": state.gate.is_licensed(), "name": state.gate.name() })
}

#[tauri::command]
pub async fn license_activate(state: State<'_, AppState>, key: String) -> Result<serde_json::Value, String> {
    use crate::license;
    let machine = state.gate.machine().to_string();
    if machine.is_empty() {
        return Err("LICENSE_MACHINE".into());
    }
    match license::activate(license::URL, &key, &machine, env!("CARGO_PKG_VERSION")).await {
        license::Remote::Ok(token) => {
            let l = state.gate.set(&*state.secrets, &token, license::PUBKEY).map_err(|e| match e {
                license::SetError::Store => "LICENSE_STORE",
                // The server signed it, so a failure here means the bundled pubkey/url is wrong.
                license::SetError::Verify => "LICENSE_CONFIG",
            })?;
            state.license_wake.notify_one();
            Ok(serde_json::json!({ "licensed": true, "name": l.name }))
        }
        other => Err(license::code(&other).into()),
    }
}

#[tauri::command]
pub fn get_settings(state: State<'_, AppState>) -> Settings {
    settings::load(&state.data_dir)
}

#[tauri::command]
pub fn save_settings(app: AppHandle, state: State<'_, AppState>, settings: Settings) -> Result<(), String> {
    let old = settings::load(&state.data_dir);
    settings::save(&state.data_dir, &settings).map_err(|e| e.to_string())?;
    if old.projects_root != settings.projects_root {
        allow_projects_root(&app, &settings.projects_root);
    }
    Ok(())
}

#[tauri::command]
pub fn set_default_logo(state: State<'_, AppState>, path: String) -> Result<Settings, String> {
    settings::set_default_logo(&state.data_dir, Path::new(&path))
}

#[tauri::command]
pub fn clear_default_logo(state: State<'_, AppState>) -> Result<Settings, String> {
    settings::clear_default_logo(&state.data_dir)
}

pub fn allow_projects_root(app: &AppHandle, root: &str) {
    let _ = std::fs::create_dir_all(root);
    let _ = app.asset_protocol_scope().allow_directory(root, true);
}

#[tauri::command]
pub fn set_api_key(state: State<'_, AppState>, key: String) -> Result<(), String> {
    state.secrets.set(API_KEY_ACCOUNT, key.trim())
}

#[tauri::command]
pub fn clear_api_key(state: State<'_, AppState>) -> Result<(), String> {
    state.secrets.delete(API_KEY_ACCOUNT)
}

#[tauri::command]
pub fn social_key_status(state: State<'_, AppState>) -> serde_json::Value {
    serde_json::json!({ "hasKey": state.secrets.get(SOCIAL_ACCOUNT).is_some() })
}

#[tauri::command]
pub fn set_social_key(state: State<'_, AppState>, key: String) -> Result<(), String> {
    state.secrets.set(SOCIAL_ACCOUNT, key.trim())
}

#[tauri::command]
pub fn clear_social_key(state: State<'_, AppState>) -> Result<(), String> {
    state.secrets.delete(SOCIAL_ACCOUNT)
}

#[tauri::command]
pub async fn eleven_status(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    Ok(eleven::status(state.secrets.as_ref(), eleven::BASE).await)
}

/// Validates the key with ElevenLabs before storing it. The key is never sent back to the UI.
#[tauri::command]
pub async fn set_eleven_key(state: State<'_, AppState>, key: String) -> Result<serde_json::Value, String> {
    let remaining = eleven::set_key(state.secrets.as_ref(), eleven::BASE, &key).await.map_err(|e| e.code().to_string())?;
    Ok(serde_json::json!({ "remaining": remaining }))
}

#[tauri::command]
pub fn clear_eleven_key(state: State<'_, AppState>) -> Result<(), String> {
    eleven::clear_key(state.secrets.as_ref(), &state.data_dir)
}

#[tauri::command]
pub async fn eleven_voices(state: State<'_, AppState>) -> Result<Vec<eleven::Voice>, String> {
    eleven::voices_for(state.secrets.as_ref(), eleven::BASE).await.map_err(|e| e.code().to_string())
}

#[tauri::command]
pub fn mcp_list(state: State<'_, AppState>) -> Vec<McpServer> {
    mcp::load(&state.data_dir)
}

#[tauri::command]
pub fn mcp_save(
    state: State<'_, AppState>,
    server: McpServer,
    secrets: std::collections::HashMap<String, String>,
) -> Result<(), String> {
    mcp::save_server(&state.data_dir, state.secrets.as_ref(), server, &secrets)
}

#[tauri::command]
pub fn mcp_delete(state: State<'_, AppState>, name: String) -> Result<(), String> {
    mcp::delete(&state.data_dir, state.secrets.as_ref(), &name)
}

#[tauri::command(async)]
pub fn engine_run(app: AppHandle, state: State<'_, AppState>, args: Vec<String>) -> Result<String, String> {
    let resource_dir = app.path().resource_dir().ok();
    let repo_root = cfg!(debug_assertions).then(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join(".."));
    let cmd = sidecar::locate_engine(resource_dir.as_deref(), repo_root.as_deref())
        .ok_or_else(|| "Không tìm thấy engine".to_string())?;
    let st = settings::load(&state.data_dir);
    let has_cc = has_claude_code_here();
    let mcp_json = mcp::engine_json(&state.data_dir, state.secrets.as_ref());
    let env = sidecar::engine_env(state.secrets.as_ref(), &st.model, has_cc, &st, &mcp_json, &args);
    let log_file = state.data_dir.join("logs").join("engine.log");
    let handle = app.clone();
    sidecar::spawn_job(&cmd, &args, &env, &log_file, state.jobs.clone(), move |msg| match msg {
        JobMsg::Event { job, event } => {
            let _ = handle.emit("engine-event", serde_json::json!({ "job": job, "event": event }));
        }
        JobMsg::Exit { job, code } => {
            let _ = handle.emit("engine-exit", serde_json::json!({ "job": job, "code": code }));
        }
    })
    .map_err(|e| format!("Không chạy được engine: {e}"))
}

#[tauri::command]
pub fn engine_cancel(state: State<'_, AppState>, job: String) {
    let jobs = state.jobs.clone();
    std::thread::spawn(move || sidecar::cancel(&jobs, &job));
}

fn projects_root(state: &AppState) -> PathBuf {
    PathBuf::from(settings::load(&state.data_dir).projects_root)
}

#[tauri::command]
#[allow(clippy::too_many_arguments)]
pub async fn create_project(
    state: State<'_, AppState>,
    niche: String,
    clips: Vec<String>,
    images: Vec<String>,
    logo: Option<String>,
    music: Option<String>,
    cta_text: Option<String>,
    name: Option<String>,
) -> Result<ProjectSummary, String> {
    let root = projects_root(&state);
    // Copying a multi-GB clip must not block the UI thread.
    tauri::async_runtime::spawn_blocking(move || {
        std::fs::create_dir_all(&root).map_err(|e| e.to_string())?;
        let today = chrono::Local::now().format("%Y-%m-%d").to_string();
        projects::create(
            &root,
            &niche,
            &clips.iter().map(PathBuf::from).collect::<Vec<_>>(),
            &images.iter().map(PathBuf::from).collect::<Vec<_>>(),
            logo.as_deref().map(Path::new),
            music.as_deref().map(Path::new),
            cta_text.as_deref().unwrap_or(""),
            name.as_deref().unwrap_or(""),
            &today,
        )
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command(async)]
pub fn list_projects(state: State<'_, AppState>) -> Vec<ProjectSummary> {
    projects::list(&projects_root(&state))
}

#[tauri::command(async)]
pub fn get_project(dir: String) -> Result<ProjectDetail, String> {
    projects::detail(Path::new(&dir))
}

#[tauri::command]
pub fn update_project(dir: String, patch: serde_json::Value) -> Result<(), String> {
    projects::update(Path::new(&dir), &patch)
}

#[tauri::command(async)]
pub fn rename_project(dir: String, name: String) -> Result<ProjectSummary, String> {
    projects::rename(Path::new(&dir), &name)
}

#[tauri::command]
pub async fn delete_project(state: State<'_, AppState>, dir: String) -> Result<(), String> {
    if state.jobs.busy_on(Path::new(&dir)) {
        return Err("Video này đang được AI xử lý, hãy dừng hoặc chờ xong rồi xoá".into());
    }
    let root = projects_root(&state);
    // A multi-GB folder can take a moment to remove.
    tauri::async_runtime::spawn_blocking(move || projects::delete(&root, Path::new(&dir)))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command(async)]
pub fn read_chat(dir: String) -> serde_json::Value {
    projects::chat(Path::new(&dir))
}

#[tauri::command(async)]
pub fn set_project_asset(dir: String, kind: String, path: Option<String>) -> Result<ProjectDetail, String> {
    projects::set_asset(Path::new(&dir), &kind, path.as_deref().map(Path::new))
}

#[tauri::command]
pub async fn set_project_media(dir: String, clips: Vec<String>, images: Vec<String>) -> Result<ProjectDetail, String> {
    // Copying large files must not block the UI thread.
    tauri::async_runtime::spawn_blocking(move || {
        projects::set_media(
            Path::new(&dir),
            &clips.iter().map(PathBuf::from).collect::<Vec<_>>(),
            &images.iter().map(PathBuf::from).collect::<Vec<_>>(),
        )
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command(async)]
pub fn set_project_voiceover(
    dir: String,
    voiceover: Option<projects::Voiceover>,
    product_info: String,
) -> Result<ProjectDetail, String> {
    projects::set_voiceover(Path::new(&dir), voiceover, &product_info)
}

#[tauri::command]
pub fn read_run_feed(dir: String, n: u64) -> Vec<FeedItem> {
    projects::run_feed(Path::new(&dir), n)
}

fn has_claude_code_here() -> bool {
    let home = dirs::home_dir().unwrap_or_default();
    auth::has_claude_code(&home, auth::mac_keychain_has_claude)
}

#[tauri::command(async)]
pub fn auth_status(state: State<'_, AppState>) -> serde_json::Value {
    serde_json::json!({ "source": auth::status(state.secrets.as_ref(), has_claude_code_here()) })
}

#[tauri::command]
pub fn login_start(app: AppHandle, state: State<'_, AppState>, cli_path: String) -> Result<(), String> {
    let mut slot = state.login.lock().map_err(|e| e.to_string())?;
    // A stale session (for example one whose screen unmounted) is replaced, not an error.
    if let Some((_, old)) = slot.take() {
        old.cancel();
    }
    let sess_id = LOGIN_GEN.fetch_add(1, Ordering::SeqCst);
    let (out, done, active) = (app.clone(), app.clone(), state.login.clone());
    let session = LoginSession::start(
        Path::new(&cli_path),
        state.secrets.clone(),
        move |l: LoginLine| {
            let _ = out.emit("login-output", l);
        },
        move |r| {
            if let Ok(mut s) = active.lock() {
                match s.as_ref() {
                    Some((g, _)) if *g != sess_id => return, // replaced by a newer session: stay silent
                    _ => *s = None,
                }
            }
            let payload = match r {
                Ok(()) => serde_json::json!({ "ok": true, "error": null }),
                Err(e) => serde_json::json!({ "ok": false, "error": e }),
            };
            let _ = done.emit("login-done", payload);
        },
    )?;
    *slot = Some((sess_id, Arc::new(session)));
    Ok(())
}

#[tauri::command]
pub fn login_input(state: State<'_, AppState>, text: String) -> Result<(), String> {
    let session = state.login.lock().map_err(|e| e.to_string())?.clone().map(|(_, s)| s);
    session.ok_or_else(|| "Chưa bắt đầu đăng nhập".to_string())?.write_input(&text)
}

#[tauri::command]
pub fn login_cancel(state: State<'_, AppState>) {
    let session = state.login.lock().ok().and_then(|s| s.clone()).map(|(_, s)| s);
    if let Some(s) = session {
        s.cancel();
    }
}

#[tauri::command]
pub fn logout(state: State<'_, AppState>) -> Result<(), String> {
    state.secrets.delete(OAUTH_ACCOUNT)
}
