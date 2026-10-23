'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowDownLeft, ArrowUpRight, Mail, Scale, Undo2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Money, SectionTitle } from '@/components/common/bits';
import { ApiError } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useT, type Key } from '@/lib/i18n';
import { todayIso } from '@/lib/live-forecast';
import { useCashChange } from '@/lib/use-cash-change';
import { useWorkspace, type CashEntry } from '@/lib/workspace';
import { cn } from '@/lib/utils';

const ICON = { INFLOW: ArrowDownLeft, OUTFLOW: ArrowUpRight, SET_BALANCE: Scale } as const;
const MODE_LABEL: Record<CashEntry['mode'], Key> = { INFLOW: 'quickCash.inflow', OUTFLOW: 'quickCash.outflow', SET_BALANCE: 'quickCash.setBalance' };

/**
 * Entries the owner typed in, newest first. A mistake is undone with an opposite entry rather than a
 * deletion, so the backend statement and this list keep the same history.
 */
export function EntriesLedger() {
  const { t } = useT();
  const { live, accountNames } = useWorkspace();
  const apply = useCashChange();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const entries = live.entries ?? [];
  if (entries.length === 0) return null;

  const reversed = new Set(entries.map((e) => e.reverses).filter(Boolean));
  const reverse = async (e: CashEntry) => {
    setBusy(e.id);
    setErr(null);
    try {
      await apply(
        e.mode === 'SET_BALANCE'
          ? { mode: 'SET_BALANCE', amount: e.previousBalance!, accountId: e.accountId, description: t('led.reversalOf', { what: e.description || t(MODE_LABEL[e.mode]) }), effectiveDate: todayIso(), reverses: e.id }
          : { mode: e.mode === 'INFLOW' ? 'OUTFLOW' : 'INFLOW', amount: e.amount, accountId: e.accountId, description: t('led.reversalOf', { what: e.description || t(MODE_LABEL[e.mode]) }), effectiveDate: todayIso(), reverses: e.id },
      );
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : t('quickCash.failed'));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="rounded-xl border bg-card p-5 md:p-6">
      <SectionTitle aside={t('led.aside')}>{t('led.title')}</SectionTitle>
      <ul className="divide-y">
        {[...entries].reverse().map((e) => {
          const Icon = ICON[e.mode];
          const done = reversed.has(e.id);
          // A first balance has nothing before it, and a reversal is not reversed again.
          // The first balance has nothing before it: it opens the account rather than correcting it.
          const title = e.description || t(e.mode === 'SET_BALANCE' && e.previousBalance === undefined ? 'led.opening' : MODE_LABEL[e.mode]);
          const canReverse = !done && !e.reverses && (e.mode !== 'SET_BALANCE' || e.previousBalance !== undefined);
          return (
            <li key={e.id} className={cn('flex items-center gap-4 py-3', done && 'opacity-60')}>
              <span
                className={cn(
                  'flex size-9 shrink-0 items-center justify-center rounded-lg',
                  e.mode === 'INFLOW' ? 'bg-good/10 text-good-text' : e.mode === 'OUTFLOW' ? 'bg-muted text-ink-2' : 'bg-accent text-accent-foreground',
                )}
                aria-hidden
              >
                <Icon className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className={cn('truncate text-sm font-medium', done && 'line-through')}>{title}</p>
                <p className="text-xs text-muted-foreground">
                  {formatDate(e.date, true)}, {accountNames[e.accountId] ?? e.accountId}
                  {done && <span className="ml-2 rounded-full bg-muted px-1.5 py-0.5 text-[11px] font-medium text-ink-2">{t('led.reversed')}</span>}
                  {e.alertId && (
                    <Link href="/bank-emails" className="ml-2 inline-flex items-center gap-1 rounded-full bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/15" title={t('led.fromEmailHint')}>
                      <Mail className="size-3" aria-hidden />
                      {t('led.fromEmail')}
                    </Link>
                  )}
                  {e.transfer && <span className="ml-2 rounded-full bg-muted px-1.5 py-0.5 text-[11px] font-medium text-ink-2">{t('be.transfer')}</span>}
                </p>
              </div>
              <div className="text-right">
                <Money
                  value={e.mode === 'OUTFLOW' ? `-${e.amount}` : e.amount}
                  signed={e.mode !== 'SET_BALANCE'}
                  className={cn('text-sm font-semibold', e.mode === 'INFLOW' && 'text-good-text')}
                />
                {e.mode === 'SET_BALANCE' && <p className="text-[11px] text-muted-foreground">{t('led.newBalance')}</p>}
              </div>
              <div className="w-24 shrink-0 text-right">
                {canReverse && (
                  <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground" disabled={busy !== null} onClick={() => reverse(e)}>
                    <Undo2 className="size-3.5" aria-hidden />
                    {busy === e.id ? t('quickCash.saving') : t('led.reverse')}
                  </Button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      {err && (
        <p className="mt-3 text-sm text-critical-text" role="alert">
          {err}
        </p>
      )}
    </section>
  );
}
