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
  const [state, setState] = useState<DataState<T>>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    if (!ready) return;
    const forced = new URLSearchParams(window.location.search).get('state');
    if (forced === 'loading') return setState({ status: 'loading' });
    if (forced === 'empty' || !hasData) return setState({ status: 'empty' });
    if (forced === 'error' && attempt === 0) {
      return setState({ status: 'error', message: 'common.timeout', retry });
    }
    if (source === 'live') {
      const data = fromLive?.(live);
      return setState(data == null ? { status: 'empty' } : { status: 'ready', data });
    }
    setState({ status: 'ready', data: load() });
    // load and fromLive are selectors; live is the data they read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, hasData, attempt, retry, source, live]);

  return state;
}
