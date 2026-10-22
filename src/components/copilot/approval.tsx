'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { Check, Copy, Download, FileText, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Money } from '@/components/common/bits';
import { centsToString, formatDate, formatDateTime, formatMoney } from '@/lib/format';
import { useT, type Key } from '@/lib/i18n';
import { ANALYSIS, BASE, COMPANY, DOSSIER, TODAY } from '@/lib/mock/demo';
import { ApiError, api } from '@/lib/api';
import { useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';
import type { IntentStatus, StagedActionIntent } from '@/lib/types';

// CashPilot works from uploaded statements with no bank or lender connection, so it never sends or
// executes anything: a drafted action becomes a request the owner sends themselves. Chat text never changes status.

export const STATUS_CLS: Record<IntentStatus, string> = {
  STAGED_PENDING_HITL: 'bg-warning/15 text-warning-text',
  PREPARED: 'bg-good/10 text-good-text',
  REJECTED: 'bg-muted text-ink-2',
  EXPIRED: 'bg-muted text-ink-2',
};

/** The intent with its current status, plus the only two status changes the UI may make. */
export function useIntentStatus(intent: StagedActionIntent) {
  const { intentStatus, intentDecidedAt, update, source } = useWorkspace();
  const { t } = useT();
  const [error, setError] = useState<string | null>(null);
  const status = intentStatus[intent.id] ?? intent.status;
  // The decision time feeds the activity panel and the audit trail.
  const set = (s: IntentStatus) =>
    update({ intentStatus: { ...intentStatus, [intent.id]: s }, intentDecidedAt: { ...intentDecidedAt, [intent.id]: new Date().toISOString() } });
  // The ledger is the record for the owner's own files: if it did not take the decision, the card stays pending.
  const decide = async (next: IntentStatus, call: (id: string) => Promise<unknown>) => {
    setError(null);
    if (source === 'live') {
      try {
        await call(intent.id);
      } catch (e) {
        return setError(e instanceof ApiError ? e.message : t('common.timeout'));
      }
    }
    set(next);
  };
  return { status, error, prepare: () => decide('PREPARED', api.prepare), dismiss: () => decide('REJECTED', api.reject) };
}

export function StatusPill({ status }: { status: IntentStatus }) {
  const { t } = useT();
  return <span className={cn('shrink-0 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium', STATUS_CLS[status])}>{t(`status.${status}` as Key)}</span>;
}

function ApprovalSteps() {
  const { t } = useT();
  const steps: [Key, Key][] = [
    ['ap.read', 'ap.readD'],
    ['ap.drafted', 'ap.draftedD'],
    ['ap.approveStep', 'ap.approveStepD'],
  ];
  return (
    <ol className="grid grid-cols-3 gap-2" aria-label={t('ap.progress')}>
      {steps.map(([label, detail], i) => {
        const complete = i < 2;
        return (
          <li key={label}>
            <div className={cn('h-1 rounded-full', complete ? 'bg-primary' : 'bg-warning')} />
            <p className="mt-2 flex items-center gap-1.5 text-sm font-medium">
              {complete && <Check className="size-3.5 text-primary" strokeWidth={3} aria-hidden />}
              {t(label)}
            </p>
            <p className="text-xs text-muted-foreground">{t(detail)}</p>
          </li>
        );
      })}
    </ol>
  );
}

/** The ready-to-send request, filled from the same calculated figures the rest of the app shows. */
function useRequestText(intent: StagedActionIntent) {
  const { t } = useT();
  const { source, live } = useWorkspace();
  const sample = source === 'sample';
  const analysis = sample ? ANALYSIS : live.analysis;
  const dossier = sample ? DOSSIER : live.underwrite?.dossier;
  const f = sample ? BASE.forecast : (live.analysis?.forecast ?? null);
  const from = analysis?.start_date ? formatDate(analysis.start_date) : '–';
  const to = analysis?.end_date ? formatDate(analysis.end_date, true) : '–';
  const money = (v: string | undefined | null) => (v ? formatMoney(v) : '–');
  return t('pr.body', {
    company: sample ? COMPANY : t('lv.company'),
    lender: intent.target_identifier,
    amount: formatMoney(centsToString(intent.amount_cents)),
    need: f?.projected_deficit_date
      ? t('pr.need', { from, to, short: formatMoney(f.projected_shortfall_amount), date: formatDate(f.projected_deficit_date ?? TODAY, true) })
      : t('pr.noNeed', { from, to }),
    cash: money(analysis?.current_balance),
    burn: money(analysis?.average_daily_burn),
    dab: money(dossier?.daily_average_balance),
    score: dossier?.liquidity_score ?? '–',
  });
}

function PrepareDialog({ intent, open, onOpenChange, onPrepared, prepared }: { intent: StagedActionIntent; open: boolean; onOpenChange: (o: boolean) => void; onPrepared: () => void; prepared: boolean }) {
  const { t } = useT();
  const [copied, setCopied] = useState(false);
  const text = useRequestText(intent);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (!prepared) onPrepared();
    } catch {
      setCopied(false);
    }
  };

  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `cashpilot-request-${intent.id}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    if (!prepared) onPrepared();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) setCopied(false);
        onOpenChange(o);
      }}
    >
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('pr.title', { lender: intent.target_identifier })}</DialogTitle>
          <DialogDescription>{t('pr.desc')}</DialogDescription>
        </DialogHeader>
        <pre className="max-h-[min(20rem,40dvh)] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/50 p-4 font-sans text-sm leading-6">{text}</pre>
        <DialogFooter className="gap-2 sm:justify-between">
          <div className="flex gap-2">
            <Button variant="outline" onClick={copy}>
              {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
              {copied ? t('reminder.copied') : t('reminder.copy')}
            </Button>
            <Button variant="outline" onClick={download}>
              <Download aria-hidden />
              {t('pr.download')}
            </Button>
          </div>
          <Button
            onClick={() => {
              if (!prepared) onPrepared();
              onOpenChange(false);
            }}
          >
            {prepared ? t('reminder.close') : t('pr.done')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Re-opens a prepared request from the audit trail, so the owner can copy it again later. */
export function ViewRequestButton({ intent }: { intent: StagedActionIntent }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        <FileText aria-hidden />
        {t('ap.view')}
      </Button>
      <PrepareDialog intent={intent} open={open} onOpenChange={setOpen} onPrepared={() => {}} prepared />
    </>
  );
}

/**
 * A drafted action with Prepare request and Dismiss. `full` is the Approvals page layout; `compact`
 * fits chat answers and the activity panel and links to the Approvals page for the record.
 */
export function ApprovalCard({ intent, variant = 'full', onNavigate }: { intent: StagedActionIntent; variant?: 'full' | 'compact'; onNavigate?: () => void }) {
  const { t } = useT();
  const { source } = useWorkspace();
  const onAssistant = usePathname() === '/assistant';
  const { status, error, prepare, dismiss } = useIntentStatus(intent);
  const [preparing, setPreparing] = useState(false);
  const pending = status === 'STAGED_PENDING_HITL';
  const prepared = status === 'PREPARED';
  const action = t(`action.${intent.action_type}` as Key);
  // Sample intents have translated rationales; live ones carry the backend's own, when it sends one.
  const whyKey = `intent.${intent.id}` as Key;
  const why = source === 'sample' ? t(whyKey, { date: formatDate(BASE.forecast.projected_deficit_date ?? TODAY) }) : intent.rationale;
  const amount = centsToString(intent.amount_cents);
  const size = variant === 'compact' ? 'sm' : 'default';

  const buttons = (pending || prepared) && (
    <div className="flex flex-wrap gap-2">
      <Button size={size} variant={prepared ? 'outline' : 'default'} onClick={() => setPreparing(true)}>
        <FileText aria-hidden />
        {prepared ? t('ap.view') : t('ap.prepare')}
      </Button>
      {pending && (
        <Button size={size} variant="outline" onClick={dismiss}>
          <X aria-hidden />
          {t('ap.reject')}
        </Button>
      )}
      {error && (
        <p className="basis-full text-sm text-critical-text" role="alert">
          {error}
        </p>
      )}
    </div>
  );
  const dialog = <PrepareDialog intent={intent} open={preparing} onOpenChange={setPreparing} onPrepared={prepare} prepared={prepared} />;

  if (variant === 'compact') {
    return (
      <div className="rounded-lg border bg-card p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs text-muted-foreground">{t('ap.from', { action, name: intent.target_identifier })}</p>
            <p className="mt-0.5 text-xl font-semibold tracking-tight">
              <Money value={amount} />
            </p>
          </div>
          <StatusPill status={status} />
        </div>
        {pending && why && <p className="mt-2 text-sm text-ink-2">{why}</p>}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          {buttons || <span />}
          {!onAssistant && <Link href="/assistant" onClick={onNavigate} className="text-xs font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
            {t('ap.open')}
          </Link>}
        </div>
        {dialog}
      </div>
    );
  }

  return (
    <article className="max-w-3xl rounded-xl border bg-card p-6">
      <ApprovalSteps />
      <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">{t('ap.from', { action, name: intent.target_identifier })}</p>
          <p className="mt-1 text-3xl font-semibold tracking-tight">
            <Money value={amount} />
          </p>
        </div>
        <p className="text-sm text-muted-foreground">{t('ap.draftedAt', { time: formatDateTime(intent.staged_at) })}</p>
      </div>
      {why && <p className="mt-4 text-sm text-ink-2">{why}</p>}
      <div className="mt-6">{buttons}</div>
      {dialog}
    </article>
  );
}
