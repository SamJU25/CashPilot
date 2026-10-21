'use client';

import Link from 'next/link';
import { Money, SeverityBadge } from '@/components/common/bits';
import { SplitFlap } from '@/components/common/split-flap';
import { formatDate } from '@/lib/format';
import { useT, type Key } from '@/lib/i18n';
import type { LiveForecast } from '@/lib/types';

const DAY_MS = 86_400_000;

/**
 * The one question the product answers, on a departure board. When What-if levers change the forecast,
 * the board shows the changed date and says what it was without them.
 */
export function ShortfallHero({
  forecast: f,
  baseForecast: b,
  changed,
  today,
  company,
  fallback,
  tools,
  actions,
  basis,
  alertThresholdDays,
}: {
  forecast: LiveForecast | null;
  baseForecast: LiveForecast | null;
  changed: boolean;
  today: string;
  company?: string;
  fallback: React.ReactNode;
  tools?: React.ReactNode;
  actions?: React.ReactNode;
  basis?: React.ReactNode;
  alertThresholdDays: number;
}) {
  const { t, rich, lang } = useT();
  const date = f?.has_projected_deficit ? f.projected_deficit_date : null;
  const overdrawn = f?.primary_deficit_trigger === 'EXISTING_OVERDRAFT';
  const days = date ? Math.round((Date.parse(date) - Date.parse(today)) / DAY_MS) : null;
  const triggerAmount = f
    ? ({ PAYROLL: f.detected_recurring_payroll, RENT: f.detected_recurring_rent, DEBT_SERVICE: f.detected_recurring_debt } as Record<string, string | null>)[f.primary_deficit_trigger ?? ''] ?? null
    : null;
  const short = f ? <Money value={f.projected_shortfall_amount} className="font-medium text-critical-text" /> : null;
  const baseDate = b?.has_projected_deficit ? b.projected_deficit_date : null;
  const sep = lang.startsWith('zh') || lang === 'ja' ? '' : ' ';

  return (
    <section aria-labelledby="hero" className="pb-2">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="flex flex-wrap items-center gap-2.5 text-sm text-muted-foreground">
          {company && <span className="font-medium text-ink-2">{company}</span>}
          {f && <SeverityBadge severity={f.severity} />}
          {changed && <span className="rounded-full bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground">{t('ov.chart.changes')}</span>}
        </div>
        {tools && <div className="flex flex-wrap gap-2">{tools}</div>}
      </div>

      <h1 id="hero" className="mt-5 max-w-4xl font-display text-[2.5rem] font-semibold leading-[1.15] tracking-tight text-balance sm:text-[3.25rem]">
        {overdrawn ? t('ov.hero.overdrawn') : date ? rich('ov.hero.short', { date: <SplitFlap text={formatDate(date)} /> }) : fallback}
      </h1>

      {date && f && (
        <p className="mt-4 max-w-[62ch] text-lg leading-relaxed text-ink-2">
          {overdrawn
            ? rich('ov.hero.whyOverdrawn', { short })
            : triggerAmount
              ? rich('ov.hero.why', { trigger: t(`trigger.${f.primary_deficit_trigger}` as Key), amount: <Money value={triggerAmount} />, short })
              : rich('ov.hero.whyBurn', { short })}
          {sep}
          {days !== null && days > 0 && t('ov.hero.days', { n: days })}
          {days === 0 && t('ov.hero.today')}
        </p>
      )}
      {changed && baseDate !== date && (
        <p className="mt-2 text-sm text-muted-foreground">
          {baseDate ? t('ov.hero.without', { date: formatDate(baseDate) }) : t('ov.hero.withoutSafe')}
        </p>
      )}

      {actions && <div className="mt-7 flex flex-wrap items-center gap-3">{actions}</div>}

      <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-muted-foreground">
        {!changed && date && days !== null && days >= 0 && days <= alertThresholdDays && (
          <Link href="/sentinel" className="inline-flex items-center gap-2 text-warning-text underline-offset-4 hover:underline">
            <span className="size-1.5 rounded-full bg-warning" aria-hidden />
            {t(days === 0 ? 'ov.alert.today' : 'ov.alert.body', { n: days, threshold: alertThresholdDays })}
          </Link>
        )}
        {basis}
      </div>
    </section>
  );
}
