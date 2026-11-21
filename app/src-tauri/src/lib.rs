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

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
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
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
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
        ])
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
