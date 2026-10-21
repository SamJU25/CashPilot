'use client';

import { motion } from 'motion/react';
import { Money, SectionTitle } from '@/components/common/bits';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cashBridge, paymentsBetween, type Point } from '@/lib/bridge';
import { centsToString, formatDate, formatMoney } from '@/lib/format';
import { useT, type Key } from '@/lib/i18n';
import { addDaysIso } from '@/lib/live-forecast';
import { spring, STAGGER_S } from '@/lib/motion';
import { cn } from '@/lib/utils';
import type { RecurringObligation } from '@/lib/types';

// List labels; the trigger.* keys are worded to sit inside a sentence.
const LABEL: Record<string, Key> = { PAYROLL: 'cat.payroll', RENT: 'cat.rent', DEBT_SERVICE: 'up.loan' };

const UPCOMING_DAYS = 45;
const UPCOMING_MAX = 5;

interface Step {
  key: string;
  label: string;
  note?: string;
  from: number;
  to: number;
  total?: boolean;
  tone: string;
}

/**
 * Why the balance falls: the forecast's start and end balances, with the recurring payments in between
 * and day-to-day spending as the remainder. The payment that tips the balance below zero is the one in colour.
 */
function Bridge({ points, obligations, endDate, shortfall }: { points: Point[]; obligations: RecurringObligation[]; endDate: string; shortfall: boolean }) {
  const { t } = useT();
  const b = cashBridge(points, obligations, endDate);
  if (!b) return null;

  const steps: Step[] = [{ key: 'start', label: t('br.start'), note: formatDate(b.start.date), from: 0, to: b.start.cents, total: true, tone: 'bg-ink-2/70' }];
  let run = b.start.cents;
  const push = (key: string, label: string, cents: number, note?: string, tone = 'bg-muted-foreground/35') => {
    steps.push({ key, label, note, from: run, to: run - cents, tone });
    run -= cents;
  };
  push('everyday', t('br.everyday'), b.everydayCents, t('br.everydayNote'));
  for (const p of b.payments) {
    const tips = shortfall && p.date === endDate && run - p.cents < 0;
    push(`${p.category}-${p.date}`, t(LABEL[p.category] ?? 'up.loan'), p.cents, formatDate(p.date), tips ? 'bg-warning' : undefined);
  }
  steps.push({ key: 'end', label: t('br.end'), note: formatDate(b.end.date), from: 0, to: b.end.cents, total: true, tone: b.end.cents < 0 ? 'bg-critical' : 'bg-ink-2/70' });

  const values = steps.flatMap((s) => [s.from, s.to]);
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const pos = (v: number) => ((v - min) / (max - min || 1)) * 100;

  return (
    <ul className="space-y-1">
          {steps.map((s, i) => {
            const lo = Math.min(s.from, s.to);
            const hi = Math.max(s.from, s.to);
            const delta = s.to - s.from;
            return (
              <li key={s.key} className="grid grid-cols-[6.5rem_1fr_6rem] items-center gap-3 py-1.5 sm:grid-cols-[10rem_1fr_7.5rem] sm:gap-4">
                <div className="min-w-0">
                  <p className={cn('truncate text-sm', s.total ? 'font-medium' : 'text-ink-2')}>{s.label}</p>
                  {s.note && <p className="truncate text-xs text-muted-foreground">{s.note}</p>}
                </div>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className="relative h-7" role="img" aria-label={`${s.label}: ${formatMoney(centsToString(s.total ? s.to : delta), undefined, { signed: !s.total })}`}>
                      <span className="absolute -inset-y-1 w-px bg-border" style={{ left: `${pos(0)}%` }} aria-hidden />
                      <motion.div
                        className={cn('absolute inset-y-2 rounded-[3px]', s.tone)}
                        style={{ left: `${pos(lo)}%`, width: `max(2px, ${pos(hi) - pos(lo)}%)`, originX: s.total || delta > 0 ? 0 : 1 }}
                        initial={{ scaleX: 0 }}
                        animate={{ scaleX: 1 }}
                        transition={{ ...spring.gentle, delay: i * STAGGER_S }}
                      />
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>{t('br.after', { amount: formatMoney(centsToString(s.to)) })}</TooltipContent>
                </Tooltip>
                <Money
                  value={centsToString(s.total ? s.to : delta)}
                  signed={!s.total}
                  className={cn('text-right text-sm', s.total ? 'font-semibold' : 'text-ink-2', s.key === 'end' && s.to < 0 && 'text-critical-text')}
                />
              </li>
            );
          })}
    </ul>
  );
}

/** The next recurring payments and what each leaves in the account. */
function Upcoming({ points, obligations, from }: { points: Point[]; obligations: RecurringObligation[]; from: string }) {
  const { t, lang } = useT();
  const balanceOn = (date: string) => points.find((p) => p.date === date)?.cents ?? null;
  const items = paymentsBetween(obligations, from, addDaysIso(from, UPCOMING_DAYS)).slice(0, UPCOMING_MAX);
  const month = new Intl.DateTimeFormat(lang, { month: 'short', timeZone: 'UTC' });

  if (items.length === 0) return <p className="text-sm text-muted-foreground">{t('up.none', { n: UPCOMING_DAYS })}</p>;
  return (
    <ol className="divide-y">
      {items.map((p) => {
        const after = balanceOn(p.date);
        const d = new Date(`${p.date}T00:00:00Z`);
        return (
          <li key={`${p.category}-${p.date}`} className="flex items-center gap-4 py-3 first:pt-0 last:pb-0">
            <div className="flex w-11 shrink-0 flex-col items-center rounded-md border bg-background py-1 leading-none">
              <span className="text-[10px] text-muted-foreground">{month.format(d)}</span>
              <span className="figures font-display text-lg font-semibold">{d.getUTCDate()}</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{t(LABEL[p.category] ?? 'up.loan')}</p>
              {after !== null && (
                <p className={cn('text-xs', after < 0 ? 'text-critical-text' : 'text-muted-foreground')}>
                  {after < 0 ? t('up.below', { amount: formatMoney(centsToString(-after)) }) : t('up.after', { amount: formatMoney(centsToString(after)) })}
                </p>
              )}
            </div>
            <Money value={centsToString(-p.cents)} className="text-sm font-medium" />
          </li>
        );
      })}
    </ol>
  );
}

export function CashFlowDetail({
  points,
  obligations,
  shortfallDate,
  today,
}: {
  points: Point[];
  obligations: RecurringObligation[];
  shortfallDate: string | null;
  today: string;
}) {
  const { t } = useT();
  if (points.length < 2) return null;
  const endDate = shortfallDate ?? points[points.length - 1].date;
  const from = today > points[0].date ? today : points[0].date;

  return (
    <section className="grid gap-px overflow-hidden rounded-xl border bg-border lg:grid-cols-[1.7fr_1fr]">
      <div className="bg-card p-5 sm:p-6">
        <SectionTitle aside={t('br.aside')}>{shortfallDate ? t('br.titleShort', { date: formatDate(shortfallDate) }) : t('br.title')}</SectionTitle>
        <Bridge points={points} obligations={obligations} endDate={endDate} shortfall={!!shortfallDate} />
      </div>
      <div className="bg-card p-5 sm:p-6">
        <SectionTitle aside={t('up.aside', { n: UPCOMING_DAYS })}>{t('up.title')}</SectionTitle>
        <Upcoming points={points} obligations={obligations} from={from} />
      </div>
    </section>
  );
}
