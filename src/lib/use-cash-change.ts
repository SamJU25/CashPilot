'use client';

// One way to change the owner's cash figures, used by the quick-cash dialog and the chat's confirmation
// card. A statement analysis keeps its accounts, dates, transfers and rejected rows; only the changed
// account, the total and what follows from them move. A manual-only workspace takes the backend's result.

import { api } from '@/lib/api';
import { centsToString, stringToCents } from '@/lib/format';
import { useT } from '@/lib/i18n';
import { useWorkspace, type CashEntry } from '@/lib/workspace';
import type { AccountSummary, CashAnalysis } from '@/lib/types';

export type CashMode = 'INFLOW' | 'OUTFLOW' | 'SET_BALANCE';

/** Each account's latest balance; one account can span several statement files. */
export function latestBalances(a: CashAnalysis | undefined): { id: string; balance: string }[] {
  const latest = new Map<string, AccountSummary>();
  for (const acc of a?.accounts_breakdown ?? []) {
    const seen = latest.get(acc.account_id);
    if (!seen || acc.end_date >= seen.end_date) latest.set(acc.account_id, acc);
  }
  return [...latest.values()].map((acc) => ({ id: acc.account_id, balance: acc.closing_balance }));
}

/** Money in and out across typed-in entries; a reversed entry and its reversal cancel, so both drop out. */
export function recordedTotals(entries: CashEntry[]): { inCents: number; outCents: number } {
  const cancelled = new Set(entries.flatMap((e) => (e.reverses ? [e.id, e.reverses] : [])));
  let inCents = 0;
  let outCents = 0;
  for (const e of entries) {
    if (cancelled.has(e.id) || e.transfer) continue;
    if (e.mode === 'INFLOW') inCents += stringToCents(e.amount);
    if (e.mode === 'OUTFLOW') outCents += stringToCents(e.amount);
  }
  return { inCents, outCents };
}

export interface CashChange {
  mode: CashMode;
  /** Plain decimal string as typed. */
  amount: string;
  description?: string;
  /** The account the change lands on; empty for an older pooled analysis. */
  accountId: string;
  /** Only when the owner typed a daily burn; otherwise the statement's burn is kept. */
  customBurn?: string;
  effectiveDate?: string;
  /** The entry this change cancels, when it is a reversal. */
  reverses?: string;
  alertId?: string;
  transfer?: boolean;
  /** Currency for a workspace this change starts; an existing one keeps its own. */
  currency?: string;
}

export function useCashChange() {
  const { t } = useT();
  const { live, setLive, update, homeCurrency, hasData, source, alertThresholdDays } = useWorkspace();
  const ownAnalysis = source === 'live' ? live.analysis : undefined;

  const entryFor = (c: CashChange, previousBalance?: string): CashEntry => ({
    id: crypto.randomUUID(),
    mode: c.mode,
    amount: c.amount,
    description: c.description,
    accountId: c.accountId,
    date: c.effectiveDate ?? new Date().toISOString().slice(0, 10),
    previousBalance,
    reverses: c.reverses,
    alertId: c.alertId,
    transfer: c.transfer,
  });

  return async function apply(c: CashChange) {
    const custom = c.customBurn?.trim() || '';
    const burn = custom || ownAnalysis?.average_daily_burn || '';
    const daily_burn = burn || undefined;
    const currency = ownAnalysis?.currency ?? c.currency ?? homeCurrency;

    if (!ownAnalysis) {
      // First entry: the owner's typed balance starts their own workspace, replacing the sample company.
      const opening = c.mode === 'OUTFLOW' ? -stringToCents(c.amount) : stringToCents(c.amount);
      const res = await api.summaryAnalyze({
        current_balance: centsToString(opening),
        daily_burn,
        currency,
        alert_threshold_days: alertThresholdDays,
        as_of_date: c.effectiveDate,
        account_name: c.accountId || t('quickCash.defaultAccount'),
      });
      setLive({ analysis: res, underwrite: undefined, receivables: undefined, intents: [], entries: [entryFor(c)] });
      if (!hasData || source !== 'live') update({ hasData: true, source: 'live', intentStatus: {}, intentDecidedAt: {} });
      return;
    }

    const accounts = latestBalances(ownAnalysis);
    const pooled = accounts.length === 0;
    const res = await api.adjustCash({
      current_balance: ownAnalysis.current_balance,
      adjustment_type: c.mode,
      amount: c.amount,
      description: c.description || undefined,
      daily_burn,
      currency,
      effective_date: c.effectiveDate,
      alert_threshold_days: alertThresholdDays,
      ...(pooled ? {} : { account_id: c.accountId, accounts: accounts.map((a) => ({ account_id: a.id, balance: a.balance })) }),
    });

    // The backend also appended this entry to the session's statement (same X-Session-ID), so the chat
    // answers from the new figures too.
    let merged: CashAnalysis = res;
    if (ownAnalysis.document_format !== 'MANUAL') {
      const burnAfter = custom ? res.average_daily_burn : ownAnalysis.average_daily_burn;
      // The forecast keeps the statement's recurring payroll, rent and debt, starting from the new balance.
      const fc = await api.scenario({
        current_balance: res.current_balance,
        average_daily_burn: burnAfter,
        anchor_date: res.end_date!,
        obligations: ownAnalysis.recurring_obligations ?? [],
      });
      // The changed account takes its new balance on its latest statement; a new account is added.
      const newBalance = res.accounts_breakdown?.find((a) => a.account_id === c.accountId)?.closing_balance;
      const breakdown = [...(ownAnalysis.accounts_breakdown ?? [])];
      const latestIdx = breakdown.reduce((best, acc, i) => (acc.account_id === c.accountId && (best < 0 || acc.end_date >= breakdown[best].end_date) ? i : best), -1);
      if (newBalance !== undefined) {
        if (latestIdx >= 0) breakdown[latestIdx] = { ...breakdown[latestIdx], closing_balance: newBalance };
        else breakdown.push({ file_name: 'manual_entry', account_id: c.accountId, start_date: res.end_date!, end_date: res.end_date!, closing_balance: newBalance, transaction_count: 1 });
      }
      merged = {
        ...ownAnalysis,
        accounts_breakdown: breakdown,
        current_balance: res.current_balance,
        average_daily_burn: burnAfter,
        runway_days: res.runway_days,
        cash_status: res.cash_status,
        projected_depletion_date: res.projected_depletion_date,
        alert_boundary_date: res.alert_boundary_date,
        forecast: fc.forecast,
        projection: fc.projection,
      };
    }
    const before = accounts.find((a) => a.id === c.accountId)?.balance ?? (pooled ? ownAnalysis.current_balance : undefined);
    setLive({ analysis: merged, entries: [...(live.entries ?? []), entryFor(c, c.mode === 'SET_BALANCE' ? before : undefined)] });
  };
}
