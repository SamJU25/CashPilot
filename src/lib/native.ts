import { invoke } from '@tauri-apps/api/core';
import { check } from '@tauri-apps/plugin-updater';

export const isNativeDesktop = (): boolean => {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
};

export interface EngineStatus {
  is_running: boolean;
  pid: number | null;
}

export interface UpdateInfo {
  available: boolean;
  version?: string;
  notes?: string;
}

/**
 * Checks for over-the-air updates from GitHub Releases.
 */
export async function nativeCheckForUpdates(): Promise<UpdateInfo> {
  if (!isNativeDesktop()) return { available: false };
  try {
    const update = await check();
    if (update) {
      return {
        available: true,
        version: update.version,
        notes: update.body ?? undefined,
      };
    }
  } catch (err) {
    console.warn('Update check failed:', err);
  }
  return { available: false };
}

/**
 * Downloads and applies the latest update, then prompts for relaunch.
 */
export async function nativeInstallUpdate(): Promise<boolean> {
  if (!isNativeDesktop()) return false;
  try {
    const update = await check();
    if (update) {
      await update.downloadAndInstall();
      return true;
    }
  } catch (err) {
    console.error('Failed to download/install update:', err);
  }
  return false;
}

/**
 * Computes SHA-256 consortium hash using native Rust (or Web Crypto fallback).
 */
export async function nativeHashInvoice(payload: string): Promise<string> {
  if (isNativeDesktop()) {
    return invoke<string>('hash_invoice', { payload });
  }
  const msgUint8 = new TextEncoder().encode(payload);
  const hashBuffer = await crypto.subtle.digest('SHA-256', msgUint8);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Checks if the supervised Python financial engine process is running.
 */
export async function nativeGetEngineStatus(): Promise<EngineStatus> {
  if (isNativeDesktop()) {
    return invoke<EngineStatus>('get_engine_status');
  }
  return { is_running: true, pid: null };
}

/**
 * Stores a credential in the native OS vault (Windows Credential Manager / macOS Keychain).
 */
export async function nativeStoreSecret(service: string, key: string, secret: string): Promise<void> {
  if (isNativeDesktop()) {
    return invoke<void>('store_secret', { service, key, secret });
  }
}

/**
 * Retrieves a credential from the native OS vault.
 */
export async function nativeGetSecret(service: string, key: string): Promise<string | null> {
  if (isNativeDesktop()) {
    try {
      return await invoke<string>('get_secret', { service, key });
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * Removes a credential from the native OS vault.
 */
export async function nativeDeleteSecret(service: string, key: string): Promise<void> {
  if (isNativeDesktop()) {
    try {
      await invoke<void>('delete_secret', { service, key });
    } catch {
      // Ignored if missing
    }
  }
}
