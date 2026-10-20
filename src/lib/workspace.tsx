'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api, resetSession } from '@/lib/api';
import { setDateLanguage, setMoneyCurrency } from '@/lib/format';
import { DEFAULT_ACCOUNT_NAMES, INTENTS } from '@/lib/mock/demo';
import { LANGUAGES, detectLanguage, type Lang } from '@/lib/i18n/languages';
import type { CashAnalysis, FinancingOption, IntentStatus, ReceivablesAgeing, StagedActionIntent, UnderwritingDossier } from '@/lib/types';

// Per-browser preferences only. Statements and drafted actions live on the backend.
const STORAGE_KEY = 'copilot.workspace.v1';
// Backend results for this tab. Tab-scoped like the chat, since they hold the business's figures.
const LIVE_KEY = 'cashpilot.live.v1';

/** What the backend returned for the owner's own files. */
export interface LiveData {
  analysis?: CashAnalysis;
  underwrite?: { dossier: UnderwritingDossier; options: FinancingOption[] };
  receivables?: ReceivablesAgeing;
  intents: StagedActionIntent[];
}
const NO_LIVE: LiveData = { intents: [] };

export type Theme = 'light' | 'dark' | 'system';

interface Prefs {
  hasData: boolean;
  /** sample: the built-in demo company; live: the owner's files, analysed by the backend. */
  source: 'sample' | 'live';
  accountNames: Record<string, string>;
  theme: Theme;
  homeCurrency: string;
  alertThresholdDays: number;
  provider: string;
  localModel: string;
  intentStatus: Record<string, IntentStatus>;
  language: Lang;
  // shortcut: keys sit in this browser's storage (as Settings tells the user); move to a backend vault for hosted use.
  providerKeys: Record<string, string>;
  providerUrls: Record<string, string>;
  providerModels: Record<string, string>;
  techDetails: boolean;
  seenRunId: string | null;
  intentDecidedAt: Record<string, string>;
}

const DEFAULTS: Prefs = {
  hasData: false,
  source: 'sample',
  accountNames: DEFAULT_ACCOUNT_NAMES,
  theme: 'system',
  homeCurrency: 'USD',
  alertThresholdDays: 30,
  provider: 'local',
  localModel: 'qwen2.5-3b-instruct',
  intentStatus: {},
  language: 'en',
  providerKeys: {},
  providerUrls: {},
  providerModels: {},
  techDetails: false,
  seenRunId: null,
  intentDecidedAt: {},
};

interface Workspace extends Prefs {
  ready: boolean;
  isLocal: boolean;
  update: (patch: Partial<Prefs>) => void;
  live: LiveData;
  setLive: (patch: Partial<LiveData>) => void;
  renameAccount: (id: string, name: string) => void;
  loadSample: () => void;
  clearData: () => void;
}

const WorkspaceContext = createContext<Workspace | null>(null);

function read(): Prefs {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    // Unreadable storage falls through to defaults.
  }
  try {
    // First visit: follow the browser language, as most websites do.
    return { ...DEFAULTS, language: detectLanguage(navigator.language) };
  } catch {
    return DEFAULTS;
  }
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [prefs, setPrefs] = useState<Prefs>(DEFAULTS);
  const [ready, setReady] = useState(false);
  const [isLocal, setIsLocal] = useState(true);
  const [live, setLiveState] = useState<LiveData>(NO_LIVE);
  setDateLanguage(prefs.language);
  // In live mode, automatically reflect the uploaded statement currency; otherwise honor homeCurrency.
  const activeCurrency = prefs.source === 'live'
    ? (live.analysis?.currency ?? live.receivables?.currency ?? prefs.homeCurrency ?? 'USD')
    : (prefs.homeCurrency ?? 'USD');
  setMoneyCurrency(activeCurrency);

  useEffect(() => {
    setPrefs(read());
    try {
      const saved = window.sessionStorage.getItem(LIVE_KEY);
      if (saved) setLiveState({ ...NO_LIVE, ...JSON.parse(saved) });
    } catch {
      // Unreadable storage: live results need a fresh upload.
    }
    setIsLocal(/^(localhost|127\.0\.0\.1|\[::1\])$|\.localhost$|\.test$/.test(window.location.hostname));
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      // Private mode or blocked storage: preferences last for this tab only.
    }
  }, [prefs, ready]);

  useEffect(() => {
    if (!ready) return;
    try {
      window.sessionStorage.setItem(LIVE_KEY, JSON.stringify(live));
    } catch {
      // Blocked storage: results last until the page reloads.
    }
  }, [live, ready]);

  useEffect(() => {
    document.documentElement.lang = LANGUAGES.find((l) => l.id === prefs.language)?.htmlLang ?? 'en';
  }, [prefs.language]);

  useEffect(() => {
    const root = document.documentElement;
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => root.classList.toggle('dark', prefs.theme === 'dark' || (prefs.theme === 'system' && media.matches));
    apply();
    media.addEventListener('change', apply);
    return () => media.removeEventListener('change', apply);
  }, [prefs.theme]);

  const update = useCallback((patch: Partial<Prefs>) => setPrefs((p) => ({ ...p, ...patch })), []);
  const setLive = useCallback((patch: Partial<LiveData>) => setLiveState((l) => ({ ...l, ...patch })), []);
  const renameAccount = useCallback(
    (id: string, name: string) => setPrefs((p) => ({ ...p, accountNames: { ...p.accountNames, [id]: name.trim() || DEFAULT_ACCOUNT_NAMES[id] || id } })),
    [],
  );
  const loadSample = useCallback(() => {
    setLiveState(NO_LIVE);
    setPrefs((p) => ({ ...p, hasData: true, source: 'sample', accountNames: DEFAULT_ACCOUNT_NAMES }));
  }, []);
  const clearData = useCallback(() => {
    // The backend keeps the session's statement until told otherwise; a failed call still drops it from this tab.
    if (prefs.source === 'live') api.clearSession().catch(() => {}).finally(resetSession);
    setLiveState(NO_LIVE);
    setPrefs((p) => ({ ...p, hasData: false, source: 'sample', accountNames: DEFAULT_ACCOUNT_NAMES, intentStatus: {}, intentDecidedAt: {} }));
  }, [prefs.source]);

  const value = useMemo(
    () => ({ ...prefs, ready, isLocal, update, live, setLive, renameAccount, loadSample, clearData }),
    [prefs, ready, isLocal, update, live, setLive, renameAccount, loadSample, clearData],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): Workspace {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace must be used inside WorkspaceProvider');
  return ctx;
}

/** Drafted actions for the current data source, with any decision the owner made in this browser. */
export function useIntents(): StagedActionIntent[] {
  const { hasData, source, live, intentStatus } = useWorkspace();
  return useMemo(() => {
    if (!hasData) return [];
    const list = source === 'live' ? live.intents : INTENTS;
    return list.map((i) => ({ ...i, status: intentStatus[i.id] ?? i.status }));
  }, [hasData, source, live.intents, intentStatus]);
}
