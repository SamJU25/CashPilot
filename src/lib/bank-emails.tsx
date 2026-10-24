'use client';

// The alerts mailbox, shared by the app: one poller (mounted in the shell) checks the mailbox while the
// app is open and counts each ready alert into the owner's figures once; the Bank emails page reads
// the same state and changes it.

import { useEffect, useRef, useSyncExternalStore } from 'react';
import { ApiError, llmConfig, mailApi, type ChatRequest, type MailAccount, type MailAlert, type MailState } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { latestBalances, useCashChange } from '@/lib/use-cash-change';
import { useWorkspace } from '@/lib/workspace';

// shortcut: polls the mailbox every minute while the app is open; IMAP IDLE would push within seconds.
export const POLL_MS = 60_000;
export const NEW_ACCOUNT = '__new__';

interface Snapshot {
  state: MailState | null;
  loading: boolean;
  syncing: boolean;
  error: ApiError | null;
  checkedAt: number | null;
}

let snap: Snapshot = { state: null, loading: true, syncing: false, error: null, checkedAt: null };
let activeActionId = 0;
const subs = new Set<() => void>();
const set = (patch: Partial<Snapshot>) => {
  snap = { ...snap, ...patch };
  subs.forEach((f) => f());
};

export function clearMailError() {
  set({ error: null });
}

export function useMail(): Snapshot {
  return useSyncExternalStore(
    (f) => (subs.add(f), () => subs.delete(f)),
    () => snap,
    () => snap,
  );
}

const asError = (e: unknown) => (e instanceof ApiError ? e : new ApiError(0, 'UNKNOWN', String(e)));

/** Runs a change and takes the state it returns; failures stay on the snapshot for the page to show. */
export async function mailDo(fn: () => Promise<MailState>): Promise<MailState | null> {
  const actionId = ++activeActionId;
  set({ loading: !snap.state, error: null });
  try {
    const state = await fn();
    if (actionId < activeActionId) {
      return null;
    }
    set({ state, error: null, loading: false });
    return state;
  } catch (e) {
    if (actionId < activeActionId) {
      return null;
    }
    set({ error: asError(e), loading: false });
    return null;
  }
}

/** Disconnects a specific mailbox or all mailboxes, immediately invalidating any running sync. */
export async function disconnectMail(address?: string): Promise<MailState | null> {
  activeActionId++;
  set({ syncing: false, loading: true, error: null });
  return mailDo(() => mailApi.disconnect(address));
}

function getCurrentLlmConfig(): ChatRequest['llm_config'] | undefined {
  try {
    const raw = typeof window !== 'undefined' ? window.localStorage.getItem('copilot.workspace.v1') : null;
    if (!raw) return undefined;
    const prefs = JSON.parse(raw);
    const provider = prefs.provider || 'local';
    const keys = prefs.providerKeys || {};
    const urls = prefs.providerUrls || {};
    const models = prefs.providerModels || {};
    const defaultUrl = provider === 'ollama' ? 'http://localhost:11434' : '';
    const selectedModel = provider === 'local' ? prefs.localModel : models[provider];
    return llmConfig(provider, keys, urls, defaultUrl, selectedModel);
  } catch {
    return undefined;
  }
}

export async function checkMail() {
  if (snap.syncing) return;
  set({ syncing: true, error: null });
  try {
    await mailDo(() => (snap.state?.connection ? mailApi.sync(getCurrentLlmConfig()) : mailApi.state()));
  } finally {
    set({ syncing: false, checkedAt: Date.now() });
  }
}

/** The display name of the account an alert's bank account is linked to. */
export const newAccountId = (a: Pick<MailAccount, 'bank' | 'tail'>) => `${a.bank} ••${a.tail}`;

/** Why a ready alert is not counted into the figures yet, or null when it will be. */
export function holdReason(a: MailAlert, ctx: { currency?: string; statementEnd?: string; sample: boolean }): 'sample' | 'currency' | 'statement' | null {
  if (ctx.sample) return 'sample';
  if (ctx.currency && a.currency !== ctx.currency) return 'currency';
  if (ctx.statementEnd && a.occurred_on <= ctx.statementEnd) return 'statement';
  return null;
}

/** Mounted once in the shell: keeps the mailbox checked and counts ready alerts into the workspace. */
export function BankEmailSync() {
  const { t } = useT();
  const mail = useMail();
  const { ready, hasData, source, live, update } = useWorkspace();
  const apply = useCashChange();
  const busy = useRef(false);
  const failed = useRef(new Set<string>());

  useEffect(() => {
    if (!ready) return;
    checkMail();
    const id = window.setInterval(() => snap.state?.connection && checkMail(), POLL_MS);
    return () => window.clearInterval(id);
  }, [ready]);

  // One alert per pass: each change re-renders with fresh figures before the next is applied.
  useEffect(() => {
    const state = mail.state;
    if (!ready || busy.current || !state?.connection) return;
    const analysis = source === 'live' ? live.analysis : undefined;
    const ctx = {
      sample: hasData && source !== 'live',
      // With no figures yet, the first bank account counted sets the workspace currency.
      currency: analysis?.currency,
      // A statement already holds everything up to its last day; a manual workspace holds nothing.
      statementEnd: analysis && analysis.document_format !== 'MANUAL' ? analysis.end_date ?? undefined : undefined,
    };
    const applied = new Set((live.entries ?? []).map((e) => e.alertId).filter(Boolean));
    const accounts = new Map(state.accounts.map((a) => [a.key, a]));
    const next = [...state.alerts]
      .reverse()
      .find((a) => a.status === 'ready' && !applied.has(a.id) && !failed.current.has(a.id) && holdReason(a, ctx) === null);
    if (!next) return;
    const acc = accounts.get(`${next.bank_domain}|${next.account_tail}|${next.currency}`);
    if (!acc?.target) return;

    const accountId = acc.target === NEW_ACCOUNT ? newAccountId(acc) : acc.target;
    const known = latestBalances(analysis).some((b) => b.id === accountId);
    const description = next.counterparty || newAccountId(acc);
    // An account CashPilot has no balance for starts from the bank's own figure in the email.
    const change =
      !known && next.balance_after
        ? { mode: 'SET_BALANCE' as const, amount: next.balance_after, description: t('be.openingFrom', { bank: newAccountId(acc) }) }
        : { mode: next.direction === 'IN' ? ('INFLOW' as const) : ('OUTFLOW' as const), amount: next.amount, description };

    busy.current = true;
    if (!analysis) update({ homeCurrency: next.currency });
    apply({ ...change, accountId, effectiveDate: next.occurred_on, alertId: next.id, transfer: !!next.transfer_with, currency: next.currency })
      .catch((e) => {
        failed.current.add(next.id);
        set({ error: asError(e) });
      })
      .finally(() => {
        busy.current = false;
        // Wake the effect for the next alert even if nothing else changed.
        set({});
      });
  }, [mail.state, ready, hasData, source, live, update, apply, t]);

  return null;
}
