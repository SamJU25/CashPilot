'use client';

import { useState } from 'react';
import { ArrowDownLeft, ArrowUpRight, Info, Plus, Scale } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { DatePicker } from '@/components/ui/date-picker';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { ApiError } from '@/lib/api';
import { latestBalances, useCashChange } from '@/lib/use-cash-change';
import { useWorkspace } from '@/lib/workspace';
import { useT, type Key } from '@/lib/i18n';
import { centsToString, currencySymbol, formatMoney, stringToCents } from '@/lib/format';
import { todayIso } from '@/lib/live-forecast';
import { cn } from '@/lib/utils';

type Mode = 'INFLOW' | 'OUTFLOW' | 'SET_BALANCE';

// A plain decimal amount as typed: digits with up to 4 decimals (the backend's numeric(18,4)).
const MONEY_INPUT = /^\d{1,14}(\.\d{0,4})?$/;
const NEW_ACCOUNT = '__new__';

const MODES: { id: Mode; label: Key; icon: typeof Plus; on: string }[] = [
  { id: 'INFLOW', label: 'quickCash.inflow', icon: ArrowDownLeft, on: 'text-good-text' },
  { id: 'OUTFLOW', label: 'quickCash.outflow', icon: ArrowUpRight, on: 'text-foreground' },
  { id: 'SET_BALANCE', label: 'quickCash.setBalance', icon: Scale, on: 'text-accent-foreground' },
];

// Worded so the backend's description rules recognise payroll, rent and loan payments for the forecast.
const SUGGEST: Record<Mode, Key[]> = {
  INFLOW: ['qc.s.customer', 'qc.s.loanIn', 'qc.s.owner'],
  OUTFLOW: ['qc.s.supplier', 'qc.s.payroll', 'qc.s.rent', 'qc.s.loanOut', 'qc.s.tax'],
  SET_BALANCE: [],
};

interface Props {
  trigger?: React.ReactNode;
  variant?: 'outline' | 'default' | 'ghost';
  size?: 'default' | 'sm' | 'lg';
  className?: string;
  defaultMode?: Mode;
}

export function QuickCashDialog({ trigger, variant = 'outline', size = 'default', className, defaultMode = 'INFLOW' }: Props) {
  const { t } = useT();
  const { live, homeCurrency, source, hasData, accountNames } = useWorkspace();
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
  const [effectiveDate, setEffectiveDate] = useState(todayIso);

  // The sample company's figures never mix with the owner's own entries.
  const ownAnalysis = source === 'live' ? live.analysis : undefined;
  const replacesSample = hasData && source === 'sample';
  const currBalance = ownAnalysis?.current_balance ?? '0.00';
  // Burn comes only from the owner's statements or what they type; never a guessed default.
  const burn = customBurn.trim() || ownAnalysis?.average_daily_burn || '';
  const currency = ownAnalysis?.currency ?? homeCurrency;

  // Which account the change lands on. No accounts yet (first entry) means naming the first one.
  const accounts = latestBalances(ownAnalysis);
  const pooled = !!ownAnalysis && accounts.length === 0; // older analyses without a breakdown
  const selected = accountSel || accounts[0]?.id || NEW_ACCOUNT;
  const isNew = !pooled && selected === NEW_ACCOUNT;
  // The placeholder name is the default, so an empty field never blocks saving.
  const accountId = isNew ? newName.trim() || t('quickCash.defaultAccount') : selected;
  const label = (id: string) => accountNames[id] ?? id;
  const nameTaken = isNew && accounts.some((a) => a.id.toLowerCase() === accountId.toLowerCase() || label(a.id).toLowerCase() === accountId.toLowerCase());
  const validName = !isNew || (accountId.length > 0 && accountId.length <= 80 && !nameTaken);
  // A new account starts from the balance entered.
  const effectiveMode: Mode = isNew ? 'SET_BALANCE' : mode;
  const firstEntry = !ownAnalysis;

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
      await applyChange({ mode: effectiveMode, amount: amount.trim(), description: desc.trim() || undefined, accountId, customBurn, effectiveDate });
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
            <Plus className="size-4" aria-hidden />
            {t('quickCash.trigger')}
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl font-semibold tracking-tight">{t(firstEntry ? 'quickCash.titleFirst' : 'quickCash.title')}</DialogTitle>
          <DialogDescription>{t(firstEntry ? 'quickCash.descFirst' : 'quickCash.desc')}</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-5">
          {replacesSample && (
            <p className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-ink-2">
              <Info className="mt-0.5 size-3.5 shrink-0 text-warning-text" aria-hidden />
              {t('quickCash.sampleNote')}
            </p>
          )}

          {/* A first entry is always a starting balance, so the choice only appears once one exists. */}
          {!firstEntry && (
            <div role="radiogroup" aria-label={t('quickCash.kind')} className={cn('grid grid-cols-3 gap-1 rounded-xl bg-muted p-1', isNew && 'pointer-events-none opacity-50')}>
              {MODES.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  role="radio"
                  aria-checked={effectiveMode === m.id}
                  onClick={() => setMode(m.id)}
                  className={cn(
                    'flex h-10 items-center justify-center gap-1.5 rounded-lg text-sm font-medium transition-colors',
                    effectiveMode === m.id ? cn('bg-card shadow-sm', m.on) : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  <m.icon className="size-4" aria-hidden />
                  {t(m.label)}
                </button>
              ))}
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-[1fr_10rem]">
            <div className="space-y-1.5">
              <Label htmlFor="qc-amount">{t(effectiveMode === 'SET_BALANCE' ? 'quickCash.balanceLabel' : 'quickCash.amount')}</Label>
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-display text-xl text-muted-foreground">{currencySymbol(currency).trim()}</span>
                <Input
                  id="qc-amount"
                  type="text"
                  inputMode="decimal"
                  required
                  autoFocus
                  placeholder="0.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ''))}
                  aria-invalid={amount !== '' && !validAmount}
                  className="figures h-12 pl-9 font-display text-2xl font-semibold"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="qc-date">{t('quickCash.date')}</Label>
              <DatePicker id="qc-date" value={effectiveDate} onChange={setEffectiveDate} max={todayIso()} className="h-12" />
            </div>
          </div>

          {effectiveMode !== 'SET_BALANCE' && (
            <div className="space-y-1.5">
              <Label htmlFor="qc-desc">{t('quickCash.descLabel')}</Label>
              <Input id="qc-desc" type="text" placeholder={t('quickCash.descPlaceholder')} value={desc} onChange={(e) => setDesc(e.target.value)} />
              <div className="flex flex-wrap gap-1.5 pt-1">
                {SUGGEST[effectiveMode].map((k) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setDesc(t(k))}
                    className={cn('rounded-full border px-2.5 py-1 text-xs transition-colors', desc === t(k) ? 'border-primary bg-accent text-accent-foreground' : 'text-ink-2 hover:bg-muted')}
                  >
                    {t(k)}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Which account, or the name of a new one; pooled older analyses have no accounts to pick. */}
          {!pooled && (
            <div className="space-y-1.5">
              <Label htmlFor={accounts.length > 0 ? 'qc-account' : 'qc-account-name'}>{t('quickCash.account')}</Label>
              {accounts.length > 0 && (
                <Select value={selected} onValueChange={setAccountSel}>
                  <SelectTrigger id="qc-account">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {accounts.map((a) => (
                      <SelectItem key={a.id} value={a.id}>
                        {label(a.id)} <span className="figures text-muted-foreground">{formatMoney(a.balance)}</span>
                      </SelectItem>
                    ))}
                    <SelectItem value={NEW_ACCOUNT}>{t('quickCash.newAccount')}</SelectItem>
                  </SelectContent>
                </Select>
              )}
              {isNew && (
                <Input
                  id="qc-account-name"
                  type="text"
                  maxLength={80}
                  placeholder={t('quickCash.defaultAccount')}
                  aria-label={t('quickCash.accountName')}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
              )}
              {nameTaken && <p className="text-xs text-critical-text">{t('quickCash.nameTaken')}</p>}
            </div>
          )}

          {/* Spend is asked for only when nothing else gives it: a first balance with no statements. */}
          {firstEntry && (
            <div className="space-y-1.5">
              <Label htmlFor="qc-burn">
                {t('quickCash.dailyBurn')} <span className="font-normal text-muted-foreground">({t('quickCash.optional')})</span>
              </Label>
              <Input id="qc-burn" type="text" inputMode="decimal" placeholder="0.00" value={customBurn} onChange={(e) => setCustomBurn(e.target.value)} className="figures" />
              <p className="text-xs text-muted-foreground">{t('quickCash.burnHelp')}</p>
            </div>
          )}

          <dl className="space-y-2 rounded-xl bg-muted/50 p-4 text-sm">
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">{t(isNew || firstEntry ? 'quickCash.startsAt' : 'quickCash.current')}</dt>
              <dd className="figures">{formatMoney(centsToString(accountCents))}</dd>
            </div>
            <div className="flex items-center justify-between font-medium">
              <dt>{t('quickCash.projected')}</dt>
              <dd className={cn('figures font-display text-lg font-semibold', accountAfter < accountCents && 'text-ink-2', accountAfter > accountCents && 'text-good-text')}>
                {formatMoney(centsToString(accountAfter))}
              </dd>
            </div>
            {showTotal && (
              <div className="flex items-center justify-between border-t pt-2 text-muted-foreground">
                <dt>{t('quickCash.total')}</dt>
                <dd className="figures">{formatMoney(centsToString(totalAfter))}</dd>
              </div>
            )}
            {projectedRunway !== null && (
              <div className="flex items-center justify-between border-t pt-2 text-muted-foreground">
                <dt>{t('quickCash.runway')}</dt>
                <dd className="figures">
                  {currentRunway !== null && currentRunway !== projectedRunway ? `${t('quickCash.days', { n: currentRunway })} → ` : ''}
                  <span className="font-medium text-foreground">{t('quickCash.days', { n: projectedRunway })}</span>
                </dd>
              </div>
            )}
          </dl>

          {err && (
            <p className="text-sm text-critical-text" role="alert">
              {err}
            </p>
          )}

          <DialogFooter className="gap-2 sm:gap-0">
            <DialogClose asChild>
              <Button type="button" variant="ghost" disabled={busy}>
                {t('quickCash.cancel')}
              </Button>
            </DialogClose>
            <Button type="submit" disabled={busy || !validAmount || !validBurn || !validName}>
              {busy ? t('quickCash.saving') : t(effectiveMode === 'SET_BALANCE' ? 'quickCash.saveBalance' : 'quickCash.save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
