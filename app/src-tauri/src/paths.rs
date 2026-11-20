use std::path::PathBuf;

/// Same location as `engine/autoedit/bins.py:app_data_dir`.
pub fn app_data_dir() -> PathBuf {
    if cfg!(target_os = "macos") {
        dirs::home_dir().unwrap_or_default().join("Library").join("Application Support").join("AutoEdit")
    } else if cfg!(windows) {
        std::env::var_os("APPDATA")
            .map(PathBuf::from)
            .or_else(dirs::home_dir)
            .unwrap_or_default()
            .join("AutoEdit")
    } else {
        dirs::home_dir().unwrap_or_default().join(".local").join("share").join("AutoEdit")
    }
}

pub fn default_projects_root() -> PathBuf {
    dirs::video_dir()
        .or_else(|| dirs::home_dir().map(|h| h.join("Videos")))
        .unwrap_or_default()
        .join("AutoEdit")
}

#[allow(dead_code)] // used by engine_run (next task)
pub fn logs_dir() -> PathBuf {
    app_data_dir().join("logs")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dirs_end_with_autoedit() {
        assert!(app_data_dir().ends_with("AutoEdit"));
        assert!(default_projects_root().ends_with("AutoEdit"));
        assert!(logs_dir().ends_with("AutoEdit/logs"));
    }
}
