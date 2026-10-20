'use client';

import Link from 'next/link';
import { useMemo } from 'react';
import { AlertOctagon, AlertTriangle, Info, ListChecks, ShieldCheck, ShieldX } from 'lucide-react';
import { TierBadge } from '@/components/common/bits';
import { centsToString, formatDate, formatDateTime, formatMoney } from '@/lib/format';
import { useT, type Key } from '@/lib/i18n';
import { ALERTS, BASE, OVERDUE_INVOICE, buildRuns, type AlertSeverity } from '@/lib/mock/demo';
import { useIntents, useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';
import type { AgentRun } from '@/lib/types';

export type FeedItem =
  | { kind: 'alert'; id: string; at: string; severity: AlertSeverity; title: string; body: string; href: string }
  | { kind: 'run'; id: string; at: string; run: AgentRun }
  | { kind: 'decision'; id: string; at: string; approved: boolean; title: string; body: string };

/** Everything the agent did or raised, newest first. Decisions are the owner's own actions, so they never count as unread. */
export function useFeed() {
  const { accountNames, hasData, source, intentStatus, intentDecidedAt } = useWorkspace();
  const intents = useIntents();
  const { t, lang } = useT();

  return useMemo<FeedItem[]>(() => {
    if (!hasData) return [];
    // shortcut: live alerts and runs need GET /events (handoff item 3); until then only the owner's decisions show.
    const sample = source === 'sample';
    const f = BASE.forecast;
    const alertText: Record<(typeof ALERTS)[number]['id'], [string, string]> = {
      shortfall: [
        t('feed.shortfall.title', { date: formatDate(f.projected_deficit_date!) }),
        t('feed.shortfall.body', { payroll: formatMoney(f.detected_recurring_payroll!), short: formatMoney(f.projected_shortfall_amount) }),
      ],
      overdue: [
        t('feed.overdue.title', { name: OVERDUE_INVOICE.customer, days: OVERDUE_INVOICE.days_overdue }),
        t('feed.overdue.body', { amount: formatMoney(centsToString(OVERDUE_INVOICE.cents)), later: formatDate('2026-11-01') }),
      ],
      gap: [
        t('feed.gap.title', { account: accountNames.Account_2, from: formatDate('2026-09-01'), to: formatDate('2026-09-07') }),
        t('feed.gap.body'),
      ],
    };
    const alerts: FeedItem[] = !sample ? [] : ALERTS.map((a) => ({ kind: 'alert', id: `alert_${a.id}`, at: a.at, severity: a.severity, href: a.href, title: alertText[a.id][0], body: alertText[a.id][1] }));
    const runs: FeedItem[] = !sample ? [] : buildRuns(accountNames, t).map((run) => ({ kind: 'run', id: run.id, at: run.started_at, run }));
    const decisions: FeedItem[] = intents.filter((i) => intentDecidedAt[i.id]).map((i) => {
      const approved = intentStatus[i.id] === 'PREPARED';
      const action = t(`action.${i.action_type}` as Key);
      const amount = formatMoney(centsToString(i.amount_cents));
      return {
        kind: 'decision',
        id: `decision_${i.id}`,
        at: intentDecidedAt[i.id],
        approved,
        title: t(approved ? 'feed.approved.title' : 'feed.rejected.title', { action }),
        body: t(approved ? 'feed.approved.body' : 'feed.rejected.body', { amount, lender: i.target_identifier }),
      };
    });
    return [...alerts, ...runs, ...decisions].sort((a, b) => b.at.localeCompare(a.at));
    // lang is a dependency because dates inside the text are formatted per language.
  }, [accountNames, hasData, source, intents, intentStatus, intentDecidedAt, t, lang]);
}

const ALERT_ICON = {
  critical: { icon: AlertOctagon, cls: 'bg-critical/10 text-critical-text' },
  warning: { icon: AlertTriangle, cls: 'bg-warning/15 text-warning-text' },
  info: { icon: Info, cls: 'bg-muted text-ink-2' },
} as const;

export function FeedRow({ item, onNavigate }: { item: FeedItem; onNavigate?: () => void }) {
  const { t } = useT();
  const time = (
    <time dateTime={item.at} className="figures text-xs text-muted-foreground">
      {formatDateTime(item.at)}
    </time>
  );

  if (item.kind === 'run') {
    return (
      <div className="flex gap-3">
        <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground" aria-hidden>
          <ListChecks className="size-3.5" />
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <p className="text-sm font-medium">{item.run.trigger}</p>
            <TierBadge tier={item.run.tier} />
          </div>
          {time}
          <p className="mt-1 text-sm text-ink-2">{item.run.outcome}</p>
        </div>
      </div>
    );
  }

  const visual =
    item.kind === 'alert'
      ? ALERT_ICON[item.severity]
      : item.approved
        ? { icon: ShieldCheck, cls: 'bg-good/10 text-good-text' }
        : { icon: ShieldX, cls: 'bg-muted text-ink-2' };

  return (
    <div className="flex gap-3">
      <span className={cn('mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full', visual.cls)} aria-hidden>
        <visual.icon className="size-3.5" />
      </span>
      <div className="min-w-0">
        <p className="text-sm font-medium">{item.title}</p>
        {time}
        <p className="mt-1 text-sm text-ink-2">{item.body}</p>
        {item.kind === 'alert' && (
          <Link href={item.href} onClick={onNavigate} className="mt-1 inline-block text-xs font-medium text-primary underline-offset-2 hover:underline">
            {t('feed.view')}
          </Link>
        )}
      </div>
    </div>
  );
}
