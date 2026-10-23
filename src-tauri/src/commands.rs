use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::State;
use crate::EngineProcess;

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct EngineStatus {
  pub is_running: bool,
  pub pid: Option<u32>,
}

#[tauri::command]
pub fn hash_invoice(payload: String) -> String {
  let mut hasher = Sha256::new();
  hasher.update(payload.as_bytes());
  hex::encode(hasher.finalize())
}

#[tauri::command]
pub fn get_engine_status(engine: State<'_, EngineProcess>) -> EngineStatus {
  let mut guard = engine.0.lock().unwrap();
  if let Some(child) = guard.as_mut() {
    match child.try_wait() {
      Ok(None) => EngineStatus {
        is_running: true,
        pid: Some(child.id()),
      },
      _ => EngineStatus {
        is_running: false,
        pid: None,
      },
    }
  } else {
    EngineStatus {
      is_running: false,
      pid: None,
    }
  }
}

#[tauri::command]
pub fn store_secret(service: String, key: String, secret: String) -> Result<(), String> {
  let entry = keyring::Entry::new(&service, &key).map_err(|e| e.to_string())?;
  entry.set_password(&secret).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_secret(service: String, key: String) -> Result<String, String> {
  let entry = keyring::Entry::new(&service, &key).map_err(|e| e.to_string())?;
  entry.get_password().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn delete_secret(service: String, key: String) -> Result<(), String> {
  let entry = keyring::Entry::new(&service, &key).map_err(|e| e.to_string())?;
  entry.delete_credential().map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
  use super::*;

  #[test]
  fn test_hash_invoice_sha256() {
    let payload = "INV-2026-001|10000.00|USD";
    let hash = hash_invoice(payload.to_string());
    assert_eq!(hash.len(), 64);
    // Known SHA-256 output for INV-2026-001|10000.00|USD
    assert_eq!(
      hash,
      "ffde8975784ff2e7fa99b309d56862ea5c681805f7970bef9116d7e724f27af6"
    );
  }
}
