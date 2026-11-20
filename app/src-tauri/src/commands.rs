use std::path::PathBuf;
use std::sync::Arc;

use tauri::{AppHandle, Emitter, Manager, State};

use crate::secrets::{SecretStore, API_KEY_ACCOUNT};
use crate::settings::{self, Settings};
use crate::sidecar::{self, JobMsg, Jobs};

pub struct AppState {
    pub secrets: Arc<dyn SecretStore + Send + Sync>,
    pub data_dir: PathBuf,
    pub jobs: Arc<Jobs>,
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
    // TODO(task 6): replace `false` with auth::has_claude_code(...)
    let env = sidecar::engine_env(state.secrets.as_ref(), &model, false);
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
