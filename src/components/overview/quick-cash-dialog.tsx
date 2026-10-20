'use client';

import { useState } from 'react';
import { ArrowDownLeft, ArrowUpRight, Coins } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { ApiError } from '@/lib/api';
import { latestBalances, useCashChange } from '@/lib/use-cash-change';
import { useWorkspace } from '@/lib/workspace';
import { useT } from '@/lib/i18n';
import { centsToString, formatMoney, stringToCents } from '@/lib/format';
import { cn } from '@/lib/utils';

type Mode = 'INFLOW' | 'OUTFLOW' | 'SET_BALANCE';

// A plain decimal amount as typed: digits with up to 4 decimals (the backend's numeric(18,4)).
const MONEY_INPUT = /^\d{1,14}(\.\d{0,4})?$/;
const NEW_ACCOUNT = '__new__';

interface Props {
  trigger?: React.ReactNode;
  variant?: 'outline' | 'default' | 'ghost';
  size?: 'default' | 'sm' | 'lg';
  className?: string;
  defaultMode?: Mode;
}

export function QuickCashDialog({ trigger, variant = 'outline', size = 'default', className, defaultMode = 'INFLOW' }: Props) {
  const { t } = useT();
  const { live, homeCurrency, source, accountNames } = useWorkspace();
  const applyChange = useCashChange();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>(defaultMode);
  const [amount, setAmount] = useState('');
  const [desc, setDesc] = useState('');
  const [customBurn, setCustomBurn] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [accountSel, setAccountSel] = useState('');
  const [newName, setNewName] = useState('');

  // The sample company's figures never mix with the owner's own entries.
  const ownAnalysis = source === 'live' ? live.analysis : undefined;
  const currBalance = ownAnalysis?.current_balance ?? '0.00';
  // Burn comes only from the owner's statements or what they type; never a guessed default.
  const burn = customBurn.trim() || ownAnalysis?.average_daily_burn || '';
  const currency = ownAnalysis?.currency ?? homeCurrency;

  // Which account the change lands on. No accounts yet (first entry) means naming the first one.
  const accounts = latestBalances(ownAnalysis);
  const pooled = !!ownAnalysis && accounts.length === 0; // older analyses without a breakdown
  const selected = accountSel || accounts[0]?.id || NEW_ACCOUNT;
  const isNew = !pooled && selected === NEW_ACCOUNT;
  const accountId = isNew ? newName.trim() : selected;
  const label = (id: string) => accountNames[id] ?? id;
  const nameTaken = isNew && accounts.some((a) => a.id.toLowerCase() === accountId.toLowerCase() || label(a.id).toLowerCase() === accountId.toLowerCase());
  const validName = !isNew || (accountId.length > 0 && accountId.length <= 80 && !nameTaken);
  // A new account starts from the balance entered.
  const effectiveMode: Mode = isNew ? 'SET_BALANCE' : mode;

  // Integer cents throughout, so the preview matches the backend's Decimal result.
  const validAmount = MONEY_INPUT.test(amount.trim());
  const validBurn = burn === '' || MONEY_INPUT.test(burn);
  const totalCents = stringToCents(currBalance);
  const accountCents = pooled ? totalCents : isNew ? 0 : stringToCents(accounts.find((a) => a.id === selected)?.balance ?? '0');
  const amtCents = validAmount ? stringToCents(amount.trim()) : 0;
  const burnCents = validBurn && burn ? stringToCents(burn) : 0;
  const accountAfter = effectiveMode === 'INFLOW' ? accountCents + amtCents : effectiveMode === 'OUTFLOW' ? accountCents - amtCents : amtCents;
  const totalAfter = totalCents - accountCents + accountAfter;
  const runwayFor = (cents: number) => (burnCents > 0 ? (cents <= 0 ? 0 : Math.floor(cents / burnCents)) : null);
  const currentRunway = ownAnalysis ? runwayFor(totalCents) : null;
  const projectedRunway = runwayFor(totalAfter);
  const showTotal = !!ownAnalysis && !pooled && (accounts.length > 1 || isNew);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validAmount || !validBurn || !validName) return;
    setBusy(true);
    setErr(null);
    try {
      await applyChange({
        mode: effectiveMode,
        amount: amount.trim(),
        description: desc.trim() || undefined,
        accountId,
        customBurn,
      });
      setOpen(false);
      setAmount('');
      setDesc('');
      setCustomBurn('');
      setNewName('');
      setAccountSel('');
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : t('quickCash.failed'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant={variant} size={size} className={cn('gap-2', className)}>
            <Coins className="h-4 w-4" />
            {t('quickCash.trigger')}
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl font-semibold">
            <Coins className="h-5 w-5 text-primary" />
            {t('quickCash.title')}
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            {t('quickCash.desc')}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-5 pt-2">
          {/* Account: an existing one, or a new one (its balance is set from the amount). */}
          {!pooled && (
            <div className="space-y-1.5">
              <Label htmlFor="qc-account" className="text-xs font-medium text-muted-foreground">
                {t('quickCash.account')}
              </Label>
              {accounts.length > 0 && (
                <select
                  id="qc-account"
                  value={selected}
                  onChange={(e) => setAccountSel(e.target.value)}
                  className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                >
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {label(a.id)} ({formatMoney(a.balance)})
                    </option>
                  ))}
                  <option value={NEW_ACCOUNT}>{t('quickCash.newAccount')}</option>
                </select>
              )}
              {isNew && (
                <Input
                  id={accounts.length > 0 ? 'qc-account-name' : 'qc-account'}
                  type="text"
                  maxLength={80}
                  placeholder={t('quickCash.defaultAccount')}
                  aria-label={t('quickCash.accountName')}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="text-base sm:text-sm"
                />
              )}
              {nameTaken && <p className="text-xs text-critical-text">{t('quickCash.nameTaken')}</p>}
            </div>
          )}

          {/* Mode Switcher: a new account starts from a set balance. */}
          <div className={cn('grid grid-cols-3 gap-1 rounded-lg border bg-muted/40 p-1 text-xs font-medium', isNew && 'pointer-events-none opacity-50')} aria-disabled={isNew}>
            <button
              type="button"
              onClick={() => setMode('INFLOW')}
              className={cn(
                'flex items-center justify-center gap-1.5 rounded-md py-2 transition-all',
                mode === 'INFLOW'
                  ? 'bg-background text-good-text shadow-sm font-semibold'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <ArrowDownLeft className="h-3.5 w-3.5" />
              {t('quickCash.inflow')}
            </button>
            <button
              type="button"
              onClick={() => setMode('OUTFLOW')}
              className={cn(
                'flex items-center justify-center gap-1.5 rounded-md py-2 transition-all',
                mode === 'OUTFLOW'
                  ? 'bg-background text-warning-text shadow-sm font-semibold'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <ArrowUpRight className="h-3.5 w-3.5" />
              {t('quickCash.outflow')}
            </button>
            <button
              type="button"
              onClick={() => setMode('SET_BALANCE')}
              className={cn(
                'flex items-center justify-center gap-1.5 rounded-md py-2 transition-all',
                mode === 'SET_BALANCE'
                  ? 'bg-background text-foreground shadow-sm font-semibold'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Coins className="h-3.5 w-3.5" />
              {t('quickCash.setBalance')}
            </button>
          </div>

          {/* Amount input */}
          <div className="space-y-1.5">
            <Label htmlFor="qc-amount" className="text-xs font-medium text-muted-foreground">
              {t('quickCash.amount')} ({currency})
            </Label>
            <div className="relative">
              <Input
                id="qc-amount"
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                required
                autoFocus
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="font-mono text-lg tabular-nums tracking-tight"
              />
            </div>
          </div>

          {/* Description input */}
          <div className="space-y-1.5">
            <Label htmlFor="qc-desc" className="text-xs font-medium text-muted-foreground">
              {t('quickCash.descLabel')}
            </Label>
            <Input
              id="qc-desc"
              type="text"
              placeholder={t('quickCash.descPlaceholder')}
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              className="text-sm"
            />
          </div>

          {/* Daily burn configuration when setting initial balance or refining */}
          {(!live.analysis || mode === 'SET_BALANCE') && (
            <div className="space-y-1.5">
              <Label htmlFor="qc-burn" className="text-xs font-medium text-muted-foreground">
                {t('quickCash.dailyBurn')} ({t('quickCash.perDay', { currency })})
              </Label>
              <Input
                id="qc-burn"
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                placeholder={ownAnalysis?.average_daily_burn ?? '0.00'}
                value={customBurn}
                onChange={(e) => setCustomBurn(e.target.value)}
                className="font-mono text-sm tabular-nums"
              />
            </div>
          )}

          {/* Live Impact Preview Card */}
          <div className="rounded-lg border bg-muted/30 p-3.5 space-y-2 text-xs">
            <div className="flex items-center justify-between text-muted-foreground">
              <span>{t('quickCash.current')}</span>
              <span className="font-mono font-medium text-foreground tabular-nums">
                {formatMoney(centsToString(accountCents))}
              </span>
            </div>
            <div className="flex items-center justify-between font-medium">
              <span>{t('quickCash.projected')}</span>
              <span
                className={cn(
                  'font-mono tabular-nums font-semibold',
                  accountAfter >= accountCents ? 'text-good-text' : 'text-warning-text'
                )}
              >
                {formatMoney(centsToString(accountAfter))}
              </span>
            </div>
            {showTotal && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span>{t('quickCash.total')}</span>
                <span className="font-mono tabular-nums">
                  {formatMoney(currBalance)} → <strong className="text-foreground">{formatMoney(centsToString(totalAfter))}</strong>
                </span>
              </div>
            )}
            <div className="flex items-center justify-between pt-1 border-t text-muted-foreground">
              <span>{t('quickCash.runway')}</span>
              {projectedRunway === null ? (
                <span>{t('quickCash.noBurn')}</span>
              ) : (
                <span className="font-mono tabular-nums">
                  {currentRunway !== null ? `${t('quickCash.days', { n: currentRunway })} → ` : ''}
                  <strong className="text-foreground">{t('quickCash.days', { n: projectedRunway })}</strong>
                </span>
              )}
            </div>
          </div>

          {err && <p className="text-xs text-destructive font-medium">{err}</p>}

          <DialogFooter className="gap-2 sm:gap-0">
            <DialogClose asChild>
              <Button type="button" variant="ghost" disabled={busy}>
                {t('quickCash.cancel')}
              </Button>
            </DialogClose>
            <Button type="submit" disabled={busy || !validAmount || !validBurn || !validName}>
              {busy ? t('quickCash.saving') : t('quickCash.save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
