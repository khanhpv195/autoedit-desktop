use std::path::PathBuf;
use std::sync::Arc;

use tauri::{AppHandle, Manager, State};

use crate::secrets::{SecretStore, API_KEY_ACCOUNT};
use crate::settings::{self, Settings};

pub struct AppState {
    pub secrets: Arc<dyn SecretStore + Send + Sync>,
    pub data_dir: PathBuf,
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
