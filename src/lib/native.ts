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
  currentVersion?: string;
  notes?: string;
  date?: string;
  downloadUrl?: string;
  isNative?: boolean;
}

function compareVersions(v1: string, v2: string): number {
  const c1 = v1.replace(/^v/, '').split('.').map((x) => parseInt(x, 10) || 0);
  const c2 = v2.replace(/^v/, '').split('.').map((x) => parseInt(x, 10) || 0);
  for (let i = 0; i < Math.max(c1.length, c2.length); i++) {
    const a = c1[i] ?? 0;
    const b = c2[i] ?? 0;
    if (a > b) return 1;
    if (a < b) return -1;
  }
  return 0;
}

/**
 * Checks for over-the-air updates from GitHub Releases (desktop Tauri or web fallback).
 */
export async function nativeCheckForUpdates(currentVersion = '1.0.0'): Promise<UpdateInfo> {
  const isNative = isNativeDesktop();
  if (isNative) {
    try {
      const update = await check();
      if (update) {
        return {
          available: true,
          version: update.version,
          currentVersion: update.currentVersion,
          notes: update.body ?? undefined,
          date: update.date ?? undefined,
          isNative: true,
        };
      }
      return { available: false, currentVersion, isNative: true };
    } catch (err) {
      console.warn('Native update check failed, attempting web fallback:', err);
    }
  }

  // Universal fallback: check GitHub Releases API
  try {
    const res = await fetch('https://api.github.com/repos/SamJU25/CashPilot/releases/latest', {
      headers: { Accept: 'application/vnd.github.v3+json' },
    });
    if (res.ok) {
      const release = await res.json();
      const latestTag = (release.tag_name || '').replace(/^v/, '');
      const hasNewer = compareVersions(latestTag, currentVersion) > 0;
      return {
        available: hasNewer,
        version: release.tag_name,
        currentVersion,
        notes: release.body || undefined,
        date: release.published_at || undefined,
        downloadUrl: release.html_url || 'https://github.com/SamJU25/CashPilot/releases',
        isNative,
      };
    }
  } catch (err) {
    console.warn('Web update check failed:', err);
  }

  return { available: false, currentVersion, isNative };
}

/**
 * Downloads and applies the latest update, invoking progress callbacks.
 */
export async function nativeInstallUpdate(
  onProgress?: (downloaded: number, total: number | null) => void
): Promise<boolean> {
  if (!isNativeDesktop()) return false;
  try {
    const update = await check();
    if (update) {
      let downloaded = 0;
      let total: number | null = null;
      await update.downloadAndInstall((event) => {
        if (event.event === 'Started') {
          total = event.data.contentLength ?? null;
        } else if (event.event === 'Progress') {
          downloaded += event.data.chunkLength;
          if (onProgress) onProgress(downloaded, total);
        }
      });
      return true;
    }
  } catch (err) {
    console.error('Failed to download/install update:', err);
    throw err;
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
