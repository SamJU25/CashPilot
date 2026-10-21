'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ErrorState } from '@/components/common/states';
import { Money, SectionTitle, SeverityBadge } from '@/components/common/bits';
import { KeyFigures } from '@/components/overview/key-figures';
import { WorkingCapitalCard } from '@/components/overview/working-capital-card';
import { RunwayChart, type ChartHistory } from '@/components/overview/runway-chart';
import { ApiError } from '@/lib/api';
import { addDaysIso, liveHistory, liveProjection, runScenario, todayIso } from '@/lib/live-forecast';
import { WhatIf } from '@/components/overview/what-if';
import { centsToString, formatDate, formatMoney, stringToCents } from '@/lib/format';
import { ANALYSIS, ANCHOR, BASE, BASE_SCENARIO, COMPANY, INTENTS, OVERDUE_INVOICE, RECEIVABLES, SERIES, TODAY, TOTAL_SERIES, project, type Projection, type Scenario } from '@/lib/mock/demo';
import { spring } from '@/lib/motion';
import { useData } from '@/lib/use-data';
import { useIntents, useWorkspace } from '@/lib/workspace';
import type { CashAnalysis } from '@/lib/types';
import { useT, type Key } from '@/lib/i18n';
import { QuickCashDialog } from '@/components/overview/quick-cash-dialog';
import { ShortfallHero } from '@/components/overview/hero';
import { SplitFlap } from '@/components/common/split-flap';

const SAMPLE_HISTORY: ChartHistory = {
  total: TOTAL_SERIES,
  accounts: SERIES.map((s) => ({ account_id: s.account_id, points: s.points.map((p) => ({ date: p.date, cents: p.balance === null ? null : stringToCents(p.balance) })) })),
};

/** Page-level tools: entering cash and refreshing statements sit with the page, away from the decision buttons. */
function PageTools() {
  const { t } = useT();
  return (
    <>
      <QuickCashDialog size="sm" />
      <Button asChild size="sm" variant="ghost">
        <Link href="/statements">{t('ov.hero.update')}</Link>
      </Button>
    </>
  );
}

function Welcome() {
  const { loadSample } = useWorkspace();
  const { t } = useT();
  return (
    <section className="mx-auto max-w-2xl py-16 sm:py-24">
      <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">{t('ov.welcome.title')}</h1>
      <p className="mt-4 text-base text-ink-2">{t('ov.welcome.body')}</p>
      <div className="mt-8 flex flex-wrap gap-3">
        <Button asChild size="lg">
          <Link href="/statements">{t('common.add')}</Link>
        </Button>
        <QuickCashDialog defaultMode="SET_BALANCE" size="lg" trigger={<Button variant="outline" size="lg">{t('quickCash.triggerDirect')}</Button>} />
        <Button variant="ghost" size="lg" onClick={loadSample}>
          {t('ov.welcome.sample')}
        </Button>
      </div>
      <p className="mt-6 text-sm text-muted-foreground">{t('ov.welcome.note')}</p>
    </section>
  );
}

/**
 * The owner's own files. Only what /analyze returns is shown; the dated forecast, chart and what-if
 * levers join once the backend sends the forecast and series (handoff items 1 to 3).
 */
function LiveOverview({ analysis: a }: { analysis: CashAnalysis }) {
  const { t, rich } = useT();
  const { live, alertThresholdDays } = useWorkspace();
  const pending = useIntents().find((i) => i.status === 'STAGED_PENDING_HITL');
  const today = todayIso();
  const f = a.forecast ?? null;
  const base = useMemo(() => liveProjection(a), [a]);
  const history = useMemo(() => liveHistory(a), [a]);
  const [scenario, setScenario] = useState<Scenario>(BASE_SCENARIO);
  const [result, setResult] = useState<Projection | null>(null);
  const [scenarioError, setScenarioError] = useState<string | null>(null);
  const changed = scenario.cutPct > 0 || scenario.extraMonthlyCents > 0 || scenario.collectInvoice;

  // The collection lever supports all overdue receivables or specific delinquent debtors.
  const debtors = useMemo(() => {
    if (!live.receivables) return [];
    return (live.receivables.top_debtors ?? []).filter((d) => stringToCents(d.overdue_amount) > 0);
  }, [live.receivables]);

  const overdue = live.receivables && stringToCents(live.receivables.total_overdue) > 0 ? live.receivables.total_overdue : null;
  const collectDate = f ? addDaysIso(f.anchor_date > today ? f.anchor_date : today, 7) : today;

  const collectOptions = useMemo(() => {
    if (!overdue) return [];
    const opts = [{ id: 'ALL', name: t('whatif.allOverdue'), amount: overdue }];
    for (const d of debtors) {
      opts.push({ id: d.customer_name, name: d.customer_name, amount: d.overdue_amount });
    }
    return opts;
  }, [overdue, debtors, t]);

  const activeDebtorId = scenario.selectedDebtorId ?? 'ALL';
  const chosenAmount = useMemo(() => {
    if (!overdue) return '0.00';
    if (activeDebtorId === 'ALL') return overdue;
    const match = debtors.find((d) => d.customer_name === activeDebtorId);
    return match ? match.overdue_amount : overdue;
  }, [overdue, activeDebtorId, debtors]);

  const collect = overdue
    ? {
        label: t('lv.collect'),
        note: t('lv.collectNote', { amount: formatMoney(chosenAmount), date: formatDate(collectDate) }),
        options: collectOptions,
        selectedId: activeDebtorId,
        onSelect: (id: string) => setScenario((prev) => ({ ...prev, selectedDebtorId: id })),
      }
    : null;

  // Levers re-run the forecast on the backend; a short pause keeps slider drags from flooding it.
  useEffect(() => {
    if (!changed || !base) {
      setResult(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      runScenario(a, scenario, overdue ? { date: collectDate, amount: chosenAmount } : null)
        .then((r) => !cancelled && (setResult(r), setScenarioError(null)))
        .catch((e) => !cancelled && setScenarioError(e instanceof ApiError ? e.message : t('common.timeout')));
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // a, base and the collection inputs change together with the analysis.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario, a, chosenAmount, collectDate]);

  // A typed-in balance with no spend gives no runway; saying "covers 90 days" would be a claim with no basis.
  const manual = a.document_format === 'MANUAL';
  const noBurn = stringToCents(a.average_daily_burn) <= 0;
  const fallback =
    a.runway_days !== null
      ? rich('lv.hero.runway', { n: <SplitFlap text={String(a.runway_days)} /> })
      : manual && noBurn
        ? t('lv.hero.noBurn')
        : t('ov.hero.safe');
  const basis = manual
    ? t(noBurn ? 'lv.hero.manual' : 'lv.hero.manualBurn', { date: formatDate(a.end_date!, true), burn: formatMoney(a.average_daily_burn) })
    : t('lv.hero.basis', { from: formatDate(a.start_date!), to: formatDate(a.end_date!, true), burn: formatMoney(a.average_daily_burn) });

  return (
    <div className="space-y-8">
      <ShortfallHero
        forecast={changed && result ? result.forecast : f}
        baseForecast={f}
        changed={changed && !!result}
        today={today}
        fallback={fallback}
        alertThresholdDays={alertThresholdDays}
        tools={<PageTools />}
        actions={
          <>
            {pending && (
              <Button asChild size="lg">
                <Link href="/assistant">{t('ov.hero.review', { amount: formatMoney(centsToString(pending.amount_cents), undefined, { cents: false }) })}</Link>
              </Button>
            )}
            <Button asChild size="lg" variant={pending ? 'outline' : 'default'}>
              <Link href="/funding">{t('ov.hero.compare')}</Link>
            </Button>
          </>
        }
        basis={<span>{basis}</span>}
      />

      <section aria-label={t('ov.figuresAria')} className="rounded-xl border bg-card px-5 py-5 sm:px-6">
        <KeyFigures analysis={a} />
      </section>

      {base && f ? (
        <section className="grid gap-px overflow-hidden rounded-xl border bg-border xl:grid-cols-[1fr_320px]" aria-label={t('ov.forecastAria')}>
          <div className="bg-card p-5 sm:p-6">
            <SectionTitle aside={changed && result ? t('ov.chart.changes') : undefined}>{t('ov.chart.title')}</SectionTitle>
            <RunwayChart history={history} anchor={f.anchor_date} today={today} base={base} scenario={changed ? result : null} />
          </div>
          <div className="bg-card p-5 sm:p-6">
            <WhatIf scenario={scenario} onChange={setScenario} base={base} result={changed && result ? result : base} collect={collect} />
            {scenarioError && (
              <p className="mt-2 text-sm text-critical-text" role="alert">
                {scenarioError}
              </p>
            )}
          </div>
        </section>
      ) : (
        <p className="rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">{t('lv.noForecast')}</p>
      )}

      <WorkingCapitalCard analysis={a} />
    </div>
  );
}

function OverviewSkeleton() {
  const { t } = useT();
  return (
    <div className="space-y-8" aria-busy="true" aria-label={t('ov.loading')}>
      <div className="space-y-3">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
      </div>
      <Skeleton className="h-[420px] w-full rounded-xl" />
      <div className="grid grid-cols-2 gap-6 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
    </div>
  );
}

function SampleOverview({ analysis, base }: { analysis: CashAnalysis; base: Projection }) {
  const { accountNames, intentStatus, alertThresholdDays } = useWorkspace();
  const [scenario, setScenario] = useState<Scenario>(BASE_SCENARIO);
  const result = useMemo(() => project(scenario), [scenario]);
  const { t } = useT();

  const f = base.forecast;
  const changed = scenario.cutPct > 0 || scenario.extraMonthlyCents > 0 || scenario.collectInvoice;
  const pending = INTENTS.find((i) => (intentStatus[i.id] ?? i.status) === 'STAGED_PENDING_HITL');

  const sampleDebtors = RECEIVABLES.top_debtors.filter((d) => stringToCents(d.overdue_amount) > 0);
  const sampleCollectOptions = [
    { id: 'ALL', name: t('whatif.allOverdue'), amount: RECEIVABLES.total_overdue },
    ...sampleDebtors.map((d) => ({ id: d.customer_name, name: d.customer_name, amount: d.overdue_amount })),
  ];
  const activeSampleDebtorId = scenario.selectedDebtorId ?? 'ALL';
  const sampleDebtor = sampleDebtors.find((d) => d.customer_name === activeSampleDebtorId);
  const chosenSampleAmount = activeSampleDebtorId === 'ALL' ? RECEIVABLES.total_overdue : (sampleDebtor?.overdue_amount ?? centsToString(OVERDUE_INVOICE.cents));
  // "All" quotes the oldest invoice's lateness.
  const chosenSampleDays = sampleDebtor?.max_days_overdue ?? Math.max(...sampleDebtors.map((d) => d.max_days_overdue));

  return (
    <div className="space-y-8">
      <ShortfallHero
        forecast={changed ? result.forecast : f}
        baseForecast={f}
        changed={changed}
        today={TODAY}
        company={COMPANY}
        fallback={t('ov.hero.safe')}
        alertThresholdDays={alertThresholdDays}
        tools={<PageTools />}
        actions={
          <>
            {pending && (
              <Button asChild size="lg">
                <Link href="/assistant">{t('ov.hero.review', { amount: formatMoney(centsToString(pending.amount_cents), undefined, { cents: false }) })}</Link>
              </Button>
            )}
            <Button asChild size="lg" variant={pending ? 'outline' : 'default'}>
              <Link href="/funding">{t('ov.hero.compare')}</Link>
            </Button>
          </>
        }
        basis={<span>{t('ov.hero.basis', { n: analysis.accounts_breakdown?.length ?? 1, from: formatDate(analysis.start_date!), to: formatDate(analysis.end_date!, true) })}</span>}
      />

      <section aria-label={t('ov.figuresAria')} className="rounded-xl border bg-card px-5 py-5 sm:px-6">
        <KeyFigures analysis={analysis} />
      </section>

      <section className="grid gap-px overflow-hidden rounded-xl border bg-border xl:grid-cols-[1fr_320px]" aria-label={t('ov.forecastAria')}>
        <div className="bg-card p-5 sm:p-6">
          <SectionTitle aside={changed ? t('ov.chart.changes') : undefined}>{t('ov.chart.title')}</SectionTitle>
          <RunwayChart
            history={SAMPLE_HISTORY}
            anchor={ANCHOR}
            today={TODAY}
            base={base}
            scenario={changed ? result : null}
            gapNote={t('chart.gapNote', { name: accountNames.Account_2, from: formatDate('2026-09-01'), to: formatDate('2026-09-07') })}
          />
        </div>
        <div className="bg-card p-5 sm:p-6">
          <WhatIf
            scenario={scenario}
            onChange={setScenario}
            base={base}
            result={result}
            collect={{
              label: t('lv.collect'),
              note: t('whatif.collectNote', { amount: formatMoney(chosenSampleAmount), days: chosenSampleDays, date: formatDate(OVERDUE_INVOICE.expected) }),
              options: sampleCollectOptions,
              selectedId: activeSampleDebtorId,
              onSelect: (id: string) => setScenario((prev) => ({ ...prev, selectedDebtorId: id })),
            }}
          />
        </div>
      </section>

      <WorkingCapitalCard analysis={analysis} />
    </div>
  );
}

export default function OverviewPage() {
  const state = useData(() => ({ analysis: ANALYSIS, base: BASE }));
  const { source, live } = useWorkspace();

  if (source === 'live') return live.analysis ? <LiveOverview analysis={live.analysis} /> : <Welcome />;
  if (state.status === 'empty') return <Welcome />;
  if (state.status === 'loading') return <OverviewSkeleton />;
  if (state.status === 'error') return <ErrorState message={state.message} retry={state.retry} />;

  return <SampleOverview analysis={state.data.analysis} base={state.data.base} />;
}
