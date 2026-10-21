'use client';

import Link from 'next/link';
import { ArrowUpRight, Info } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Money } from '@/components/common/bits';
import { CompareBars, Donut, Gauge, Legend, MiniArea, MiniBars, type Segment } from '@/components/charts/kit';
import { BUCKET_COLORS } from '@/components/charts/colors';
import { debtServiceCoverage } from '@/lib/dscr';
import { centsToString, formatDate, formatMoney, stringToCents } from '@/lib/format';
import { useT, type Key } from '@/lib/i18n';
import { weeklyNet, type DailyPoint } from '@/lib/series';
import { cn } from '@/lib/utils';
import type { CashAnalysis, FinancingOption, ReceivablesAgeing } from '@/lib/types';

const GAUGE_DAYS = 90;

/** A dashboard panel: title row with an optional link to the page that owns the detail. */
export function Panel({ title, href, linkLabel, children, className }: { title: string; href?: string; linkLabel?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn('flex flex-col rounded-xl border bg-card p-5', className)}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-display text-lg font-semibold tracking-tight">{title}</h2>
        {href && (
          <Link href={href} className="inline-flex items-center gap-1 rounded text-xs font-medium text-muted-foreground hover:text-foreground">
            {linkLabel}
            <ArrowUpRight className="size-3.5" aria-hidden />
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

function How({ label, how, formula }: { label: string; how: string; formula: string }) {
  const { t } = useT();
  return (
    <Popover>
      <PopoverTrigger className="relative rounded p-0.5 text-muted-foreground after:absolute after:-inset-3 after:content-[''] hover:bg-muted hover:text-foreground" aria-label={t('fig.howAria', { label })}>
        <Info className="size-3.5" aria-hidden />
      </PopoverTrigger>
      <PopoverContent className="w-80 text-sm" align="start">
        <p className="font-medium">{t('fig.howTitle')}</p>
        <p className="mt-1 text-muted-foreground">{how}</p>
        <pre className="mt-3 whitespace-pre-wrap rounded bg-muted px-2.5 py-2 font-mono text-xs">{formula}</pre>
      </PopoverContent>
    </Popover>
  );
}

/** Days until the shortfall on a 0 to 90 day dial, with the warning window marked. */
export function RunwayGauge({ days, windowDays }: { days: number | null; windowDays: number }) {
  const { t } = useT();
  const shown = days ?? GAUGE_DAYS;
  const tone = days === null ? 'text-good' : days <= 0 ? 'text-critical' : days <= windowDays ? 'text-warning' : 'text-good';
  return (
    <Panel title={t('dash.runway')} href="/sentinel" linkLabel={t('nav.sentinel')}>
      <div className="flex flex-1 flex-col justify-center">
        <Gauge value={shown} max={GAUGE_DAYS} threshold={windowDays} tone={tone} label={t('dash.runwayAria', { n: shown, w: windowDays })}>
          <span className="figures font-display text-4xl font-semibold leading-none">{days === null ? `${GAUGE_DAYS}+` : days}</span>
          <span className="mt-1 text-xs text-muted-foreground">{t('dash.daysLeft')}</span>
        </Gauge>
        <p className="mt-4 text-center text-xs text-muted-foreground">{t('dash.windowMark', { n: windowDays })}</p>
      </div>
    </Panel>
  );
}

/** Four headline figures, each with the small chart that shows how it got there. */
export function KpiCards({ analysis: a, history, recorded }: { analysis: CashAnalysis; history: DailyPoint[]; recorded?: { inCents: number; outCents: number } | null }) {
  const { t } = useT();
  const weeks = weeklyNet(history).slice(-9);
  // Typed-in figures carry only the latest entry's flows, so their totals come from the entries themselves.
  const inCents = recorded?.inCents ?? stringToCents(a.operational_inflows ?? a.gross_inflows ?? '0');
  const outCents = recorded?.outCents ?? stringToCents(a.operational_outflows ?? a.gross_outflows ?? '0');
  const transfers = formatMoney(a.internal_transfers_excluded ?? '0');
  const accounts = a.accounts_breakdown ? new Set(a.accounts_breakdown.map((x) => x.account_id)).size : 1;
  const net = inCents - outCents;

  const card = 'flex flex-col justify-between gap-4 rounded-xl border bg-card p-5';
  const head = (label: string, how: string, formula: string) => (
    <p className="flex items-center gap-1 text-sm text-muted-foreground">
      {label}
      <How label={label} how={how} formula={formula} />
    </p>
  );

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <div className={card}>
        <div>
          {head(t('fig.cash'), t('fig.cashHow'), t('fig.cashFormula'))}
          <Money value={a.current_balance} className="mt-1 block font-display text-3xl font-semibold tracking-tight" />
          <p className="text-xs text-muted-foreground">{t('fig.cashNote', { n: accounts })}</p>
        </div>
        <MiniArea values={history.map((p) => p.cents)} label={t('fig.trendAria')} />
      </div>

      <div className={card}>
        <div>
          {head(t('fig.burn'), t('fig.burnHow'), t('fig.burnFormula', { n: a.period_days }))}
          <Money value={a.average_daily_burn} className="mt-1 block font-display text-3xl font-semibold tracking-tight" />
          <p className="text-xs text-muted-foreground">{t('dash.perMonth', { amount: formatMoney(centsToString(stringToCents(a.average_daily_burn) * 30), undefined, { cents: false }) })}</p>
        </div>
        <p className="text-xs text-muted-foreground">{t('fig.burnNote', { n: a.period_days })}</p>
      </div>

      <div className={card}>
        <div>
          <p className="text-sm text-muted-foreground">{t('dash.weekly')}</p>
          <Money value={centsToString(weeks.at(-1)?.cents ?? 0)} signed className="mt-1 block font-display text-3xl font-semibold tracking-tight" />
          <p className="text-xs text-muted-foreground">{t('dash.lastWeek')}</p>
        </div>
        <MiniBars
          values={weeks.map((w) => w.cents)}
          titles={weeks.map((w) => `${t('dash.weekOf', { date: formatDate(w.week) })}: ${formatMoney(centsToString(w.cents), undefined, { signed: true })}`)}
          label={t('dash.weeklyAria', { n: weeks.length })}
        />
      </div>

      <div className={card}>
        <div>
          {head(t('dash.inOut'), t('fig.inHow', { from: formatDate(a.start_date ?? a.end_date ?? ''), to: formatDate(a.end_date ?? '') }), t('fig.inFormula', { amount: transfers }))}
          <Money value={centsToString(net)} signed className={cn('mt-1 block font-display text-3xl font-semibold tracking-tight', net < 0 && 'text-critical-text')} />
          <p className="text-xs text-muted-foreground">{t(recorded ? 'dash.recordedNote' : 'fig.ownNote')}</p>
        </div>
        <CompareBars
          rows={[
            { label: t('fig.in'), value: inCents, display: formatMoney(centsToString(inCents), undefined, { cents: false }), tone: 'bg-primary' },
            { label: t('fig.out'), value: outCents, display: formatMoney(centsToString(outCents), undefined, { cents: false }), tone: 'bg-serious' },
          ]}
        />
      </div>
    </div>
  );
}

export function ReceivablesSummary({ data }: { data: ReceivablesAgeing | null }) {
  const { t } = useT();
  if (!data)
    return (
      <Panel title={t('nav.receivables')} href="/receivables" linkLabel={t('dash.open')}>
        <p className="text-sm text-muted-foreground">{t('dash.noInvoices')}</p>
      </Panel>
    );
  const segments: Segment[] = Object.entries(data.buckets).map(([key, b]) => ({ key, label: t(`bucket.${key}` as Key), value: stringToCents(b.amount), color: BUCKET_COLORS[key] }));
  return (
    <Panel title={t('nav.receivables')} href="/receivables" linkLabel={t('dash.open')}>
      <div className="flex flex-col items-center gap-5">
        <Donut segments={segments} label={t('rec.barAria')} size={148}>
          <span className="text-[11px] text-muted-foreground">{t('rec.overdue')}</span>
          <Money value={data.total_overdue} cents={false} className="font-display text-xl font-semibold" />
        </Donut>
        <Legend segments={segments.filter((s) => s.value > 0)} format={(v) => formatMoney(centsToString(v), undefined, { cents: false })} />
      </div>
    </Panel>
  );
}

export function FundingSummary({ options, needCents }: { options: FinancingOption[] | null; needCents: number | null }) {
  const { t } = useT();
  const best = options?.filter((o) => !o.is_predatory).sort((a, b) => b.suitability_score - a.suitability_score)[0];
  return (
    <Panel title={t('nav.funding')} href="/funding" linkLabel={t('dash.compare', { n: options?.length ?? 0 })}>
      {best ? (
        <div className="flex flex-1 flex-col justify-between gap-4">
          <div>
            <p className="text-xs text-muted-foreground">{t('fund.best')}</p>
            <p className="mt-0.5 font-medium">{best.provider}</p>
            <p className="text-sm text-muted-foreground">{t(`product.${best.product_type}` as Key)}</p>
          </div>
          <div className="grid grid-cols-2 gap-4 border-t pt-4">
            <div>
              <p className="text-xs text-muted-foreground">{t('fund.colApr')}</p>
              <p className="figures font-display text-2xl font-semibold">{best.apr_percent}%</p>
            </div>
            {needCents !== null && (
              <div>
                <p className="text-xs text-muted-foreground">{t('fund.need')}</p>
                <Money value={centsToString(needCents)} cents={false} className="font-display text-2xl font-semibold" />
              </div>
            )}
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{t('dash.noOffers')}</p>
      )}
    </Panel>
  );
}

/** Cash conversion cycle and debt cover, the two numbers a lender looks at first. */
export function HealthSummary({ analysis: a }: { analysis: CashAnalysis }) {
  const { t } = useT();
  const ccc = a.cash_conversion_cycle_days;
  const dscr = debtServiceCoverage(a);
  const dscrTone = dscr === null ? 'text-good' : dscr >= 1.25 ? 'text-good' : dscr >= 1 ? 'text-warning' : 'text-critical';
  return (
    <Panel title={t('dash.health')}>
      <div className="grid flex-1 grid-cols-2 gap-4">
        <div className="flex flex-col items-center">
          <Gauge value={ccc ?? 0} max={90} tone={ccc === null ? 'text-muted' : ccc > 45 ? 'text-warning' : 'text-good'} label={t('wc.ccc')}>
            <span className="figures font-display text-2xl font-semibold leading-none">{ccc ?? '—'}</span>
          </Gauge>
          <p className="mt-2 text-center text-xs text-muted-foreground">{t('dash.cccLabel')}</p>
        </div>
        <div className="flex flex-col items-center">
          <Gauge value={dscr === null ? 0 : Math.max(0, dscr)} max={2} threshold={1.25} tone={dscrTone} label={t('wc.dscr')}>
            <span className="figures font-display text-2xl font-semibold leading-none">{dscr === null ? '—' : dscr <= 0 ? '<0' : `${dscr.toFixed(2)}x`}</span>
          </Gauge>
          <p className="mt-2 text-center text-xs text-muted-foreground">{t('dash.dscrLabel')}</p>
        </div>
      </div>
    </Panel>
  );
}
