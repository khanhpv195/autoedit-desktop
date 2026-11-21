mod auth;
mod commands;
mod license;
mod login;
mod mcp;
mod paths;
mod projects;
mod secrets;
mod settings;
mod sidecar;

use std::sync::Arc;

use tauri::{Emitter, Manager};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let handler: fn(tauri::ipc::Invoke<tauri::Wry>) -> bool = tauri::generate_handler![
        commands::license_status,
        commands::license_activate,
        commands::get_settings,
        commands::save_settings,
        commands::set_api_key,
        commands::clear_api_key,
        commands::social_key_status,
        commands::set_social_key,
        commands::clear_social_key,
        commands::mcp_list,
        commands::mcp_save,
        commands::mcp_delete,
        commands::engine_run,
        commands::engine_cancel,
        commands::kill_all_jobs,
        commands::create_project,
        commands::list_projects,
        commands::get_project,
        commands::update_project,
        commands::set_project_asset,
        commands::set_project_media,
        commands::read_run_feed,
        commands::auth_status,
        commands::login_start,
        commands::login_input,
        commands::login_cancel,
        commands::logout,
    ];
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default().level(log::LevelFilter::Info).build(),
                )?;
            }
            let data_dir = paths::app_data_dir();
            let s = settings::load(&data_dir);
        commands::allow_projects_root(app.handle(), &s.projects_root);
            app.manage(commands::AppState {
                secrets: Arc::new(secrets::KeyringStore),
                data_dir,
                jobs: Arc::new(sidecar::Jobs::default()),
                login: Arc::new(std::sync::Mutex::new(None)),
                gate: Arc::new(license::Gate::load(&secrets::KeyringStore, license::PUBKEY)),
            });
            spawn_license_check(app.handle().clone());
            Ok(())
        })
        .invoke_handler(move |invoke| {
            // Central gate: every command (app and user-facing plugin) is refused until licensed.
            let licensed = invoke
                .message
                .webview()
                .try_state::<commands::AppState>()
                .map(|st| st.gate.is_licensed())
                .unwrap_or(false);
            if !license::allowed(invoke.message.command(), licensed) {
                invoke.resolver.reject("LICENSE_REQUIRED");
                return true;
            }
            handler(invoke)
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event
                && let Some(state) = app.try_state::<commands::AppState>()
            {
                commands::shutdown(&state);
            }
        });
}

/// At startup, then every 6 h: if the server says the key is revoked, used elsewhere or unknown,
/// lock the app and tell the UI. Network errors and 5xx are ignored (no offline limit).
fn spawn_license_check(handle: tauri::AppHandle) {
    tauri::async_runtime::spawn(async move {
        loop {
            let st = handle.state::<commands::AppState>();
            if let Some(key) = st.gate.key() {
                let r = license::check(license::URL, &key, st.gate.machine()).await;
                if matches!(r, license::Remote::Revoked | license::Remote::Used | license::Remote::Invalid) {
                    st.gate.revoke(&*st.secrets);
                    let _ = handle.emit("license-revoked", serde_json::json!({ "reason": license::code(&r) }));
                }
            }
            tokio::time::sleep(std::time::Duration::from_secs(6 * 3600)).await;
        }
    });
}
