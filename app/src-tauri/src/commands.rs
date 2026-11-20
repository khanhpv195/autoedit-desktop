use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use tauri::{AppHandle, Emitter, Manager, State};

use crate::secrets::{SecretStore, API_KEY_ACCOUNT, OAUTH_ACCOUNT};
use crate::auth;
use crate::login::{LoginLine, LoginSession};
use crate::projects::{self, FeedItem, ProjectDetail, ProjectSummary};
use crate::settings::{self, Settings};
use crate::sidecar::{self, JobMsg, Jobs};

pub struct AppState {
    pub secrets: Arc<dyn SecretStore + Send + Sync>,
    pub data_dir: PathBuf,
    pub jobs: Arc<Jobs>,
    pub login: Arc<Mutex<Option<Arc<LoginSession>>>>,
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
pub fn engine_run(app: AppHandle, state: State<'_, AppState>, args: Vec<String>) -> Result<String, String> {
    let resource_dir = app.path().resource_dir().ok();
    let repo_root = cfg!(debug_assertions).then(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join(".."));
    let cmd = sidecar::locate_engine(resource_dir.as_deref(), repo_root.as_deref())
        .ok_or_else(|| "Không tìm thấy engine".to_string())?;
    let model = settings::load(&state.data_dir).model;
    let has_cc = has_claude_code_here();
    let env = sidecar::engine_env(state.secrets.as_ref(), &model, has_cc);
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
pub fn create_project(
    state: State<'_, AppState>,
    niche: String,
    clip: String,
    logo: Option<String>,
    music: Option<String>,
) -> Result<ProjectSummary, String> {
    let root = projects_root(&state);
    std::fs::create_dir_all(&root).map_err(|e| e.to_string())?;
    let today = chrono::Local::now().format("%Y-%m-%d").to_string();
    projects::create(
        &root,
        &niche,
        Path::new(&clip),
        logo.as_deref().map(Path::new),
        music.as_deref().map(Path::new),
        &today,
    )
}

#[tauri::command]
pub fn list_projects(state: State<'_, AppState>) -> Vec<ProjectSummary> {
    projects::list(&projects_root(&state))
}

#[tauri::command]
pub fn get_project(dir: String) -> Result<ProjectDetail, String> {
    projects::detail(Path::new(&dir))
}

#[tauri::command]
pub fn update_project(dir: String, patch: serde_json::Value) -> Result<(), String> {
    projects::update(Path::new(&dir), &patch)
}

#[tauri::command]
pub fn set_project_asset(dir: String, kind: String, path: Option<String>) -> Result<ProjectDetail, String> {
    projects::set_asset(Path::new(&dir), &kind, path.as_deref().map(Path::new))
}

#[tauri::command]
pub fn read_run_feed(dir: String, n: u64) -> Vec<FeedItem> {
    projects::run_feed(Path::new(&dir), n)
}

fn has_claude_code_here() -> bool {
    let home = dirs::home_dir().unwrap_or_default();
    auth::has_claude_code(&home, auth::mac_keychain_has_claude)
}

#[tauri::command]
pub fn auth_status(state: State<'_, AppState>) -> serde_json::Value {
    serde_json::json!({ "source": auth::status(state.secrets.as_ref(), has_claude_code_here()) })
}

#[tauri::command]
pub fn login_start(app: AppHandle, state: State<'_, AppState>, cli_path: String) -> Result<(), String> {
    let mut slot = state.login.lock().map_err(|e| e.to_string())?;
    if slot.is_some() {
        return Err("Đang có một phiên đăng nhập".into());
    }
    let (out, done, active) = (app.clone(), app.clone(), state.login.clone());
    let session = LoginSession::start(
        Path::new(&cli_path),
        state.secrets.clone(),
        move |l: LoginLine| {
            let _ = out.emit("login-output", l);
        },
        move |r| {
            if let Ok(mut s) = active.lock() {
                *s = None;
            }
            let payload = match r {
                Ok(()) => serde_json::json!({ "ok": true, "error": null }),
                Err(e) => serde_json::json!({ "ok": false, "error": e }),
            };
            let _ = done.emit("login-done", payload);
        },
    )?;
    *slot = Some(Arc::new(session));
    Ok(())
}

#[tauri::command]
pub fn login_input(state: State<'_, AppState>, text: String) -> Result<(), String> {
    let session = state.login.lock().map_err(|e| e.to_string())?.clone();
    session.ok_or_else(|| "Chưa bắt đầu đăng nhập".to_string())?.write_input(&text)
}

#[tauri::command]
pub fn login_cancel(state: State<'_, AppState>) {
    let session = state.login.lock().ok().and_then(|s| s.clone());
    if let Some(s) = session {
        s.cancel();
    }
}

#[tauri::command]
pub fn logout(state: State<'_, AppState>) -> Result<(), String> {
    state.secrets.delete(OAUTH_ACCOUNT)
}
