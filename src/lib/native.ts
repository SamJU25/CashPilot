import { invoke } from '@tauri-apps/api/core';

export const isNativeDesktop = (): boolean => {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
};

export interface EngineStatus {
  is_running: boolean;
  pid: number | null;
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
