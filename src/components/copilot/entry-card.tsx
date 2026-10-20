'use client';

import { useState } from 'react';
import { ArrowDownLeft, ArrowUpRight, Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Money } from '@/components/common/bits';
import { QuickCashDialog } from '@/components/overview/quick-cash-dialog';
import { ApiError } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useT } from '@/lib/i18n';
import { latestBalances, useCashChange } from '@/lib/use-cash-change';
import { useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';
import type { ProposedEntry } from '@/lib/api';

export type EntryStatus = 'pending' | 'recorded' | 'discarded';

const NEW_ACCOUNT = '__new__';

/**
 * A cash entry read from a chat message. Only "Record it" changes the figures; the chat itself never
 * does, so a mistyped or manipulated message cannot alter the books without this click.
 */
export function EntryCard({ entry, status, onStatus }: { entry: ProposedEntry; status: EntryStatus; onStatus: (s: EntryStatus, account?: string) => void }) {
  const { t } = useT();
  const { live, source, accountNames } = useWorkspace();
  const applyChange = useCashChange();
  const ownAnalysis = source === 'live' ? live.analysis : undefined;
  const accounts = latestBalances(ownAnalysis);
  const label = (id: string) => accountNames[id] ?? id;

  // The account the message named, matched loosely against the owner's account names.
  const hint = entry.account_hint?.toLowerCase();
  const matched = hint ? accounts.find((a) => label(a.id).toLowerCase().includes(hint) || a.id.toLowerCase().includes(hint)) : undefined;
  const [accountSel, setAccountSel] = useState(matched?.id ?? (hint ? NEW_ACCOUNT : (accounts[0]?.id ?? NEW_ACCOUNT)));
  const [newName, setNewName] = useState(entry.account_hint ?? '');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const isNew = accounts.length > 0 && accountSel === NEW_ACCOUNT;
  const accountId = isNew ? newName.trim() : accountSel;
  const out = entry.adjustment_type === 'OUTFLOW';

  const record = async () => {
    setBusy(true);
    setErr(null);
    try {
      // A new account opens with this entry; money out of an account that did not exist starts it negative.
      await applyChange({
        mode: entry.adjustment_type,
        amount: entry.amount,
        description: entry.description || undefined,
        accountId,
        effectiveDate: entry.date,
      });
      onStatus('recorded', label(accountId));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : t('quickCash.failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className={cn('flex items-center gap-1.5 text-xs font-medium', out ? 'text-warning-text' : 'text-good-text')}>
            {out ? <ArrowUpRight className="size-3.5" aria-hidden /> : <ArrowDownLeft className="size-3.5" aria-hidden />}
            {out ? t('entry.out') : t('entry.in')}
          </p>
          <p className="mt-0.5 text-xl font-semibold tracking-tight">
            <Money value={entry.amount} />
          </p>
          <p className="text-sm text-ink-2">
            {entry.description ? `${entry.description} · ` : ''}
            {formatDate(entry.date, true)}
          </p>
        </div>
        {status !== 'pending' && (
          <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-ink-2">{t(status === 'recorded' ? 'entry.recordedPill' : 'entry.discardedPill')}</span>
        )}
      </div>

      {status === 'pending' && !ownAnalysis && (
        <div className="mt-3 space-y-2">
          <p className="text-sm text-ink-2">{t('entry.needBalance')}</p>
          <QuickCashDialog defaultMode="SET_BALANCE" size="sm" />
        </div>
      )}

      {status === 'pending' && ownAnalysis && (
        <div className="mt-3 space-y-3">
          {accounts.length > 0 && (
            <div className="space-y-1.5">
              <label htmlFor={`entry-account-${entry.date}-${entry.amount}`} className="text-xs font-medium text-muted-foreground">
                {t('quickCash.account')}
              </label>
              <select
                id={`entry-account-${entry.date}-${entry.amount}`}
                value={accountSel}
                onChange={(e) => setAccountSel(e.target.value)}
                className="h-9 w-full rounded-md border bg-background px-2 text-sm"
              >
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {label(a.id)}
                  </option>
                ))}
                <option value={NEW_ACCOUNT}>{t('quickCash.newAccount')}</option>
              </select>
              {isNew && (
                <Input
                  aria-label={t('quickCash.accountName')}
                  placeholder={t('quickCash.defaultAccount')}
                  maxLength={80}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="text-base sm:text-sm"
                />
              )}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={record} disabled={busy || (isNew && !accountId)}>
              <Check aria-hidden />
              {busy ? t('quickCash.saving') : t('entry.confirm')}
            </Button>
            <Button size="sm" variant="outline" onClick={() => onStatus('discarded')} disabled={busy}>
              <X aria-hidden />
              {t('entry.discard')}
            </Button>
          </div>
          {err && (
            <p className="text-sm text-critical-text" role="alert">
              {err}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
