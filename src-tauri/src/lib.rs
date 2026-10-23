use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{Manager, WindowEvent};

pub mod commands;

pub struct EngineProcess(pub Mutex<Option<Child>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .manage(EngineProcess(Mutex::new(None)))
    .invoke_handler(tauri::generate_handler![
      commands::hash_invoice,
      commands::get_engine_status,
      commands::store_secret,
      commands::get_secret,
      commands::delete_secret
    ])
    .setup(|app| {
      // 1. Logging plugin
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      // 2. Over-the-air auto-updater plugin
      app.handle().plugin(tauri_plugin_updater::Builder::new().build())?;

      // 3. Supervised Python financial engine
      let exe_dir = std::env::current_exe().ok().and_then(|p| p.parent().map(|d| d.to_path_buf()));
      let project_root = if let Some(ref dir) = exe_dir {
        if dir.join("api/main.py").exists() {
          dir.clone()
        } else if dir.join("../api/main.py").exists() {
          dir.join("..")
        } else if dir.join("../../api/main.py").exists() {
          dir.join("../..")
        } else {
          std::path::PathBuf::from(".")
        }
      } else {
        std::path::PathBuf::from(".")
      };

      let py_candidates = if cfg!(windows) {
        vec!["python", "py", "python3"]
      } else {
        vec!["python3", "python"]
      };

      let mut spawned = false;
      for py in &py_candidates {
        let mut cmd = Command::new(py);
        cmd.current_dir(&project_root)
          .env("PYTHONPATH", ".")
          .args(["-m", "api.main"]);

        #[cfg(windows)]
        {
          use std::os::windows::process::CommandExt;
          // CREATE_NO_WINDOW ensures background execution without flashing console
          cmd.creation_flags(0x08000000);
        }

        match cmd.spawn() {
          Ok(child) => {
            log::info!("Python financial engine started using '{py}' with PID: {}", child.id());
            *app.state::<EngineProcess>().0.lock().unwrap() = Some(child);
            spawned = true;
            break;
          }
          Err(err) => {
            log::debug!("Failed candidate '{py}': {err}");
          }
        }
      }

      if !spawned {
        log::warn!("Could not auto-spawn Python engine candidates. Backend may be running independently.");
      }

      Ok(())
    })
    .on_window_event(|window, event| {
      if matches!(event, WindowEvent::CloseRequested { .. } | WindowEvent::Destroyed) {
        if let Some(mut child) = window.state::<EngineProcess>().0.lock().unwrap().take() {
          log::info!("Terminating supervised Python financial engine...");
          let _ = child.kill();
        }
      }
    })
    .run(tauri::generate_context!())
    .expect("error while building tauri application");
}
