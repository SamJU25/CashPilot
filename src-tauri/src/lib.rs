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
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      // Auto-start Python financial engine
      let py_bin = if cfg!(windows) { "python" } else { "python3" };
      match Command::new(py_bin).args(["api/main.py"]).spawn() {
        Ok(child) => {
          log::info!("Python financial engine started with PID: {}", child.id());
          *app.state::<EngineProcess>().0.lock().unwrap() = Some(child);
        }
        Err(err) => {
          log::warn!("Could not auto-spawn Python engine: {err}. Backend may already be running independently.");
        }
      }

      Ok(())
    })
    .on_window_event(|window, event| {
      if let WindowEvent::Destroyed = event {
        if let Some(mut child) = window.state::<EngineProcess>().0.lock().unwrap().take() {
          log::info!("Terminating supervised Python financial engine...");
          let _ = child.kill();
        }
      }
    })
    .run(tauri::generate_context!())
    .expect("error while building tauri application");
}
