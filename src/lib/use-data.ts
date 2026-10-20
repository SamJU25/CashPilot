'use client';

import { useCallback, useEffect, useState } from 'react';
import { useWorkspace, type LiveData } from '@/lib/workspace';
import type { Key } from '@/lib/i18n';

export type DataState<T> =
  | { status: 'loading' }
  | { status: 'empty' }
  | { status: 'error'; message: Key; retry: () => void }
  | { status: 'ready'; data: T };

/**
 * Four-state data access for every screen. `load` gives the sample company; `fromLive` picks the
 * backend's results for the owner's own files and returns null when that screen has nothing yet.
 * Append ?state=loading|empty|error to any URL to review that state.
 */
export function useData<T>(load: () => T, fromLive?: (live: LiveData) => T | null | undefined): DataState<T> {
  const { hasData, ready, source, live } = useWorkspace();
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const resolve = useCallback((): DataState<T> => {
    if (!ready) return { status: 'loading' };
    if (typeof window !== 'undefined') {
      const forced = new URLSearchParams(window.location.search).get('state');
      if (forced === 'loading') return { status: 'loading' };
      if (forced === 'empty') return { status: 'empty' };
      if (forced === 'error' && attempt === 0) return { status: 'error', message: 'common.timeout', retry };
    }
    if (!hasData) return { status: 'empty' };
    if (source === 'live') {
      const data = fromLive?.(live);
      return data == null ? { status: 'empty' } : { status: 'ready', data };
    }
    return { status: 'ready', data: load() };
  }, [ready, hasData, source, live, attempt, retry, fromLive, load]);

  const [state, setState] = useState<DataState<T>>(resolve);

  useEffect(() => {
    setState(resolve());
  }, [resolve]);

  return state;
}
