'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, CheckCircle2, HandCoins, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ReminderDialog } from '@/components/receivables/reminder-dialog';
import { centsToString, formatDate, formatMoney, stringToCents } from '@/lib/format';
import { useT } from '@/lib/i18n';
import { ANALYSIS, BASE, RECEIVABLES } from '@/lib/mock/demo';
import { useIntents, useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';
import type { Debtor } from '@/lib/types';

interface Finding {
  key: string;
  tone: 'critical' | 'warning' | 'neutral' | 'good';
  icon: typeof AlertTriangle;
  text: string;
  actions: React.ReactNode;
}

const TONE = {
  critical: 'text-critical-text',
  warning: 'text-warning-text',
  neutral: 'text-muted-foreground',
  good: 'text-good',
};

/**
 * Opens the chat with what the figures already show, so the owner starts from findings and next steps
 * instead of a blank prompt. Every number comes from the same calculations as Overview and Receivables.
 */
export function Briefing({ onAsk, onReview }: { onAsk: (question: string) => void; onReview: () => void }) {
  const { t } = useT();
  const { source, live } = useWorkspace();
  const intents = useIntents();
  const [reminding, setReminding] = useState<Debtor | null>(null);

  const analysis = source === 'sample' ? ANALYSIS : live.analysis;
  const forecast = source === 'sample' ? BASE.forecast : live.analysis?.forecast;
  const receivables = source === 'sample' ? RECEIVABLES : live.receivables;
  const pending = intents.filter((i) => i.status === 'STAGED_PENDING_HITL').length;

  const findings: Finding[] = [];
  if (forecast?.has_projected_deficit && forecast.projected_deficit_date) {
    const date = formatDate(forecast.projected_deficit_date);
    findings.push({
      key: 'short',
      tone: 'critical',
      icon: AlertTriangle,
      text: t('brief.short', { date, amount: formatMoney(centsToString(Math.abs(stringToCents(forecast.projected_shortfall_amount)))) }),
      actions: (
        <>
          <Button size="sm" onClick={() => onAsk(t('brief.shortQ', { date }))}>{t('brief.shortAsk')}</Button>
          <Button asChild size="sm" variant="ghost">
            <Link href="/">{t('brief.forecast')}</Link>
          </Button>
        </>
      ),
    });
  } else if (analysis?.runway_days != null) {
    const low = analysis.cash_status === 'LOW_RUNWAY' || analysis.cash_status === 'CASH_NONPOSITIVE';
    findings.push({
      key: 'runway',
      tone: low ? 'warning' : 'good',
      icon: low ? AlertTriangle : CheckCircle2,
      text: t('brief.runway', { n: analysis.runway_days }),
      actions: (
        <Button size="sm" variant="outline" onClick={() => onAsk(t('brief.runwayQ'))}>{t('brief.runwayAsk')}</Button>
      ),
    });
  }

  const late = [...(receivables?.top_debtors ?? [])]
    .filter((d) => stringToCents(d.overdue_amount) > 0)
    .sort((a, b) => stringToCents(b.overdue_amount) - stringToCents(a.overdue_amount))[0];
  if (late) {
    findings.push({
      key: 'late',
      tone: 'warning',
      icon: HandCoins,
      text: t('brief.owed', { name: late.customer_name, amount: formatMoney(late.overdue_amount), days: late.max_days_overdue }),
      actions: <Button size="sm" variant="outline" onClick={() => setReminding(late)}>{t('rec.draft')}</Button>,
    });
  }

  if (pending > 0) {
    findings.push({
      key: 'drafts',
      tone: 'neutral',
      icon: ShieldCheck,
      text: t('brief.drafts', { n: pending }),
      actions: <Button size="sm" variant="outline" onClick={onReview}>{t('brief.review')}</Button>,
    });
  }

  if (findings.length === 0) return null;

  return (
    <section aria-labelledby="briefing-title" className="w-full rounded-xl border bg-card p-4 shadow-xs">
      <h2 id="briefing-title" className="text-sm font-medium">{t('brief.title')}</h2>
      <ul className="mt-3 divide-y">
        {findings.map((f) => (
          <li key={f.key} className="flex flex-col gap-2.5 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
            <p className="flex items-start gap-2.5 text-sm leading-relaxed">
              <f.icon className={cn('mt-0.5 size-4 shrink-0', TONE[f.tone])} aria-hidden />
              <span>{f.text}</span>
            </p>
            <div className="flex shrink-0 flex-wrap gap-2 pl-6 sm:pl-0">{f.actions}</div>
          </li>
        ))}
      </ul>
      <ReminderDialog debtor={reminding} onClose={() => setReminding(null)} />
    </section>
  );
}
