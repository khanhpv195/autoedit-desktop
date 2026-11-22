mod auth;
mod commands;
mod eleven;
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
        commands::set_default_logo,
        commands::clear_default_logo,
        commands::set_api_key,
        commands::clear_api_key,
        commands::social_key_status,
        commands::set_social_key,
        commands::clear_social_key,
        commands::eleven_status,
        commands::set_eleven_key,
        commands::clear_eleven_key,
        commands::eleven_voices,
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
        commands::rename_project,
        commands::delete_project,
        commands::read_chat,
        commands::set_project_asset,
        commands::set_project_media,
        commands::set_project_voiceover,
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
            // The default logo thumbnail in Settings is shown through the asset protocol.
            commands::allow_projects_root(app.handle(), &data_dir.join("defaults").to_string_lossy());
            app.manage(commands::AppState {
                secrets: Arc::new(secrets::KeyringStore),
                data_dir,
                jobs: Arc::new(sidecar::Jobs::default()),
                login: Arc::new(std::sync::Mutex::new(None)),
                gate: Arc::new(license::Gate::load(&secrets::KeyringStore, license::PUBKEY)),
                license_wake: Arc::new(tokio::sync::Notify::new()),
            });
            spawn_license_check(app.handle().clone());
            Ok(())
        })
        .invoke_handler(move |invoke| {
            // Central gate: every app command is refused until licensed. Plugin commands never reach this
            // handler (Tauri routes `plugin:*|*` to the plugins) and cannot unlock editing.
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

/// Background revocation check. Polls every 15 min and runs the check when 6 h of wall-clock time
/// have passed since the last attempt (so it also fires right after a laptop wakes), at startup,
/// and immediately after a successful activation. Network errors and 5xx never lock (no offline limit).
fn spawn_license_check(handle: tauri::AppHandle) {
    tauri::async_runtime::spawn(async move {
        let wake = handle.state::<commands::AppState>().license_wake.clone();
        let mut last: Option<std::time::SystemTime> = None;
        let mut verdicts = license::Verdicts::default();
        let mut forced = false;
        loop {
            let now = std::time::SystemTime::now();
            if forced || license::check_due(last, now) {
                forced = false;
                let st = handle.state::<commands::AppState>();
                if let Some(key) = st.gate.key() {
                    last = Some(now);
                    let r = license::check(license::URL, &key, st.gate.machine()).await;
                    if let Some(reason) = verdicts.apply(&r, std::time::SystemTime::now()) {
                        st.gate.revoke(&*st.secrets);
                        commands::shutdown(&st); // stop running engine jobs and the login PTY
                        let _ = handle.emit("license-revoked", serde_json::json!({ "reason": reason }));
                    }
                }
            }
            tokio::select! {
                _ = tokio::time::sleep(license::POLL_EVERY) => {}
                _ = wake.notified() => { forced = true; }
            }
        }
    });
}
