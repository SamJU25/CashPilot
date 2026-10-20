'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, ApiError, type Hardware, type LocalModel } from '@/lib/api';
import { useWorkspace } from '@/lib/workspace';
import { useT } from '@/lib/i18n';

export type InstalledState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; models: LocalModel[] };

/** GGUF models on disk in models/, as the backend scanner sees them. */
export function useInstalledModels(enabled = true) {
  const { t } = useT();
  const [state, setState] = useState<InstalledState>({ status: 'loading' });

  const refresh = useCallback(async () => {
    try {
      const res = await api.fetchModels('local');
      setState({ status: 'ready', models: res.models.filter((m) => m.installed) });
    } catch (e) {
      setState({ status: 'error', message: e instanceof ApiError ? e.message : t('lm.folderError') });
    }
  }, [t]);

  useEffect(() => {
    if (enabled) void refresh();
  }, [enabled, refresh]);

  return { state, refresh };
}

const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });

export const formatCount = (n: number) => compact.format(n);

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return '—';
  const gb = bytes / 1024 ** 3;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${Math.round(bytes / 1024 ** 2)} MB`;
}

export function formatParams(n: number | null | undefined): string | null {
  if (!n) return null;
  return n >= 1e9 ? `${(n / 1e9).toFixed(n >= 1e10 ? 0 : 1)}B` : `${Math.round(n / 1e6)}M`;
}

export function formatContext(n: number | null | undefined): string | null {
  if (!n) return null;
  return n >= 1024 ? `${Math.round(n / 1024)}K ctx` : `${n} ctx`;
}

/** Display name for a GGUF file: drops the extension and the quant suffix the badge already shows. */
export function modelLabel(m: Pick<LocalModel, 'id' | 'name' | 'quant'>): string {
  const base = m.name.replace(/\s*\(GGUF\)$/, '');
  return m.quant ? base.replace(new RegExp(`[\\s_-]*${m.quant.replace(/_/g, '[ _]')}$`, 'i'), '') || base : base;
}

/** Live RAM and VRAM: `undefined` while the first probe runs, `null` when the backend cannot be reached. */
export function useHardware() {
  const [hw, setHw] = useState<Hardware | null | undefined>(undefined);
  const refresh = useCallback(async () => {
    try {
      setHw(await api.hardware());
    } catch {
      setHw(null);
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  return { hw, refresh };
}

// llama.cpp needs room beyond the weights for the KV cache and compute buffers at a few thousand tokens of context.
export const RUNTIME_OVERHEAD_GB = 1;

export type Fit = 'gpu' | 'split' | 'memory';

/** Where a GGUF file of this size would run with the memory free right now. */
export function fitFor(sizeBytes: number | null | undefined, hw: Hardware | null | undefined): Fit | null {
  if (!sizeBytes || !hw) return null;
  const need = sizeBytes / 1024 ** 3 + RUNTIME_OVERHEAD_GB;
  if (hw.vram_free_gb !== null && need <= hw.vram_free_gb) return 'gpu';
  if (hw.ram_available_gb === null) return null;
  return need <= (hw.vram_free_gb ?? 0) + hw.ram_available_gb ? 'split' : 'memory';
}

/** The local model chat will use: the saved pick when its file is on disk, otherwise null. */
export function useActiveLocalModel(enabled = true) {
  const { localModel } = useWorkspace();
  const installed = useInstalledModels(enabled);
  const models = installed.state.status === 'ready' ? installed.state.models : [];
  return { ...installed, models, active: models.find((m) => m.id === localModel) ?? null };
}
