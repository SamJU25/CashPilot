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
import { centsToString, formatDate, formatDateTime, formatMoney, stringToCents } from '@/lib/format';
import { ANALYSIS, ANCHOR, BASE, BASE_SCENARIO, COMPANY, INTENTS, OVERDUE_INVOICE, SERIES, TODAY, TOTAL_SERIES, buildRuns, project, type Projection, type Scenario } from '@/lib/mock/demo';
import { spring } from '@/lib/motion';
import { useData } from '@/lib/use-data';
import { useIntents, useWorkspace } from '@/lib/workspace';
import type { CashAnalysis } from '@/lib/types';
import { useT, type Key } from '@/lib/i18n';
import { QuickCashDialog } from '@/components/overview/quick-cash-dialog';

const SAMPLE_HISTORY: ChartHistory = {
  total: TOTAL_SERIES,
  accounts: SERIES.map((s) => ({ account_id: s.account_id, points: s.points.map((p) => ({ date: p.date, cents: p.balance === null ? null : stringToCents(p.balance) })) })),
};

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
  const { t, rich, lang } = useT();
  const { live } = useWorkspace();
  const pending = useIntents().find((i) => i.status === 'STAGED_PENDING_HITL');
  const today = todayIso();
  const f = a.forecast ?? null;
  const base = useMemo(() => liveProjection(a), [a]);
  const history = useMemo(() => liveHistory(a), [a]);
  const [scenario, setScenario] = useState<Scenario>(BASE_SCENARIO);
  const [result, setResult] = useState<Projection | null>(null);
  const [scenarioError, setScenarioError] = useState<string | null>(null);
  const changed = scenario.cutPct > 0 || scenario.extraMonthlyCents > 0 || scenario.collectInvoice;

  // The collection lever needs a known overdue amount and states its one assumption: payment a week out.
  const overdue = live.receivables && stringToCents(live.receivables.total_overdue) > 0 ? live.receivables.total_overdue : null;
  const collectDate = f ? addDaysIso(f.anchor_date > today ? f.anchor_date : today, 7) : today;
  const collect = overdue
    ? { label: t('lv.collect'), note: t('lv.collectNote', { amount: formatMoney(overdue), date: formatDate(collectDate) }) }
    : null;

  // Levers re-run the forecast on the backend; a short pause keeps slider drags from flooding it.
  useEffect(() => {
    if (!changed || !base) {
      setResult(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      runScenario(a, scenario, overdue ? { date: collectDate, amount: overdue } : null)
        .then((r) => !cancelled && (setResult(r), setScenarioError(null)))
        .catch((e) => !cancelled && setScenarioError(e instanceof ApiError ? e.message : t('common.timeout')));
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // a, base and the collection inputs change together with the analysis.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario, a]);

  // A typed-in balance with no spend gives no runway; saying "covers 90 days" would be a claim with no basis.
  const manual = a.document_format === 'MANUAL';
  const noBurn = stringToCents(a.average_daily_burn) <= 0;
  const shortDate = f?.has_projected_deficit ? f.projected_deficit_date : null;
  const headline = shortDate
    ? t('ov.hero.short', { date: formatDate(shortDate) })
    : a.runway_days !== null
      ? t('lv.hero.runway', { n: a.runway_days })
      : manual && noBurn
        ? t('lv.hero.noBurn')
        : t('ov.hero.safe');
  const triggerAmount = f
    ? ({ PAYROLL: f.detected_recurring_payroll, RENT: f.detected_recurring_rent, DEBT_SERVICE: f.detected_recurring_debt } as Record<string, string | null>)[f.primary_deficit_trigger ?? ''] ?? null
    : null;
  const daysFromToday = shortDate ? Math.round((Date.parse(shortDate) - Date.parse(today)) / 86_400_000) : null;
  const shortNode = f ? <Money value={f.projected_shortfall_amount} className="font-medium text-critical-text" /> : null;
  const basis = manual
    ? t(noBurn ? 'lv.hero.manual' : 'lv.hero.manualBurn', { date: formatDate(a.end_date!, true), burn: formatMoney(a.average_daily_burn) })
    : t('lv.hero.basis', { from: formatDate(a.start_date!), to: formatDate(a.end_date!, true), burn: formatMoney(a.average_daily_burn) });

  return (
    <div className="space-y-12">
      <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={spring.smooth} aria-labelledby="hero">
        {f && (
          <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <SeverityBadge severity={f.severity} />
          </div>
        )}
        <h1 id="hero" className="mt-3 text-3xl font-semibold tracking-tight text-balance sm:text-[2.5rem] sm:leading-[1.15]">
          {headline}
        </h1>
        {shortDate && f && (
          <p className="mt-3 max-w-2xl text-base text-ink-2">
            {triggerAmount
              ? rich('ov.hero.why', { trigger: t(`trigger.${f.primary_deficit_trigger}` as Key), amount: <Money value={triggerAmount} />, short: shortNode })
              : rich('ov.hero.whyBurn', { short: shortNode })}
            {lang.startsWith('zh') ? '' : ' '}
            {daysFromToday !== null && daysFromToday >= 0 && t('ov.hero.days', { n: daysFromToday })}
          </p>
        )}
        <p className="mt-3 max-w-2xl text-sm text-muted-foreground">{basis}</p>
        <div className="mt-6 flex flex-wrap gap-3">
          {pending && (
            <Button asChild>
              <Link href="/assistant">{t('ov.hero.review', { amount: formatMoney(centsToString(pending.amount_cents), undefined, { cents: false }) })}</Link>
            </Button>
          )}
          <QuickCashDialog variant="default" />
          <Button asChild variant="outline">
            <Link href="/funding">{t('ov.hero.compare')}</Link>
          </Button>
          <Button asChild variant="ghost">
            <Link href="/statements">{t('ov.hero.update')}</Link>
          </Button>
        </div>
      </motion.section>

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

      <section aria-label={t('ov.figuresAria')}>
        <KeyFigures analysis={a} />
        <WorkingCapitalCard analysis={a} />
      </section>
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

export default function OverviewPage() {
  const state = useData(() => ({ analysis: ANALYSIS, base: BASE }));
  const { accountNames, intentStatus, source, live } = useWorkspace();
  const [scenario, setScenario] = useState<Scenario>(BASE_SCENARIO);
  const result = useMemo(() => project(scenario), [scenario]);
  const { t, rich, lang } = useT();
  // lang is a dependency because dates inside run text are formatted per language.
  const runs = useMemo(() => buildRuns(accountNames, t), [accountNames, t, lang]);

  if (source === 'live') return live.analysis ? <LiveOverview analysis={live.analysis} /> : <Welcome />;
  if (state.status === 'empty') return <Welcome />;
  if (state.status === 'loading') return <OverviewSkeleton />;
  if (state.status === 'error') return <ErrorState message={state.message} retry={state.retry} />;

  const { analysis, base } = state.data;
  const f = base.forecast;
  const changed = scenario.cutPct > 0 || scenario.extraMonthlyCents > 0 || scenario.collectInvoice;
  const daysFromToday = f.projected_deficit_date ? Math.round((Date.parse(f.projected_deficit_date) - Date.parse(TODAY)) / 86_400_000) : null;
  const triggerAmount = { PAYROLL: f.detected_recurring_payroll, RENT: f.detected_recurring_rent, DEBT_SERVICE: f.detected_recurring_debt }[f.primary_deficit_trigger ?? ''] ?? null;
  const pending = INTENTS.find((i) => (intentStatus[i.id] ?? i.status) === 'STAGED_PENDING_HITL');
  const latest = runs[0];
  const shortNode = <Money value={f.projected_shortfall_amount} className="font-medium text-critical-text" />;

  return (
    <div className="space-y-12">
      <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={spring.smooth} aria-labelledby="hero">
        <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
          <span>{COMPANY}</span>
          <SeverityBadge severity={f.severity} />
        </div>
        {f.has_projected_deficit ? (
          <>
            <h1 id="hero" className="mt-3 text-3xl font-semibold tracking-tight text-balance sm:text-[2.5rem] sm:leading-[1.15]">
              {t('ov.hero.short', { date: formatDate(f.projected_deficit_date!) })}
            </h1>
            <p className="mt-3 max-w-2xl text-base text-ink-2">
              {triggerAmount
                ? rich('ov.hero.why', {
                    trigger: t(`trigger.${f.primary_deficit_trigger}` as Key),
                    amount: <Money value={triggerAmount} />,
                    short: shortNode,
                  })
                : rich('ov.hero.whyBurn', { short: shortNode })}
              {lang.startsWith('zh') ? '' : ' '}
              {daysFromToday !== null && daysFromToday >= 0 && t('ov.hero.days', { n: daysFromToday })}
            </p>
          </>
        ) : (
          <h1 id="hero" className="mt-3 text-3xl font-semibold tracking-tight text-balance sm:text-[2.5rem]">
            {t('ov.hero.safe')}
          </h1>
        )}
        <div className="mt-6 flex flex-wrap gap-3">
          {pending && (
            <Button asChild>
              <Link href="/assistant">{t('ov.hero.review', { amount: formatMoney(centsToString(pending.amount_cents), undefined, { cents: false }) })}</Link>
            </Button>
          )}
          <Button asChild variant="outline">
            <Link href="/funding">{t('ov.hero.compare')}</Link>
          </Button>
        </div>
        <p className="mt-4 text-xs text-muted-foreground">
          {t('ov.hero.basis', { n: analysis.accounts_breakdown?.length ?? 1, from: formatDate(analysis.start_date!), to: formatDate(analysis.end_date!, true) })}{' '}
          <Link href="/statements" className="underline underline-offset-2 hover:text-foreground">
            {t('ov.hero.update')}
          </Link>
        </p>
      </motion.section>

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
              label: t('whatif.collect', { name: OVERDUE_INVOICE.customer }),
              note: t('whatif.collectNote', { amount: formatMoney(centsToString(OVERDUE_INVOICE.cents)), days: OVERDUE_INVOICE.days_overdue, date: formatDate(OVERDUE_INVOICE.expected) }),
            }}
          />
        </div>
      </section>

      <section aria-label={t('ov.figuresAria')}>
        <KeyFigures analysis={analysis} />
        <WorkingCapitalCard analysis={analysis} />
      </section>

      <section className="grid gap-10 border-t pt-10 lg:grid-cols-2">
        <div>
          <SectionTitle aside={<Link href="/assistant" className="hover:text-foreground">{t('ov.allApprovals')}</Link>}>{t('ov.waiting')}</SectionTitle>
          {pending ? (
            <div className="rounded-lg border bg-card p-5">
              <p className="text-sm text-muted-foreground">{t('ov.drawFrom', { name: pending.target_identifier })}</p>
              <p className="mt-1 text-2xl font-semibold tracking-tight">
                <Money value={centsToString(pending.amount_cents)} />
              </p>
              <p className="mt-2 text-sm text-ink-2">{t(`intent.${pending.id}` as Key, { date: formatDate(f.projected_deficit_date ?? TODAY) })}</p>
              <Button asChild className="mt-4">
                <Link href="/assistant">{t('ov.reviewApprove')}</Link>
              </Button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t('ov.nothing')}</p>
          )}
        </div>
        <div>
          <SectionTitle aside={<Link href="/assistant" className="hover:text-foreground">{t('ov.allActivity')}</Link>}>{t('ov.latest')}</SectionTitle>
          <p className="text-sm">{t('ov.runAt', { trigger: latest.trigger, time: formatDateTime(latest.started_at) })}</p>
          <p className="mb-2 text-sm text-muted-foreground">{latest.outcome}</p>
        </div>
      </section>
    </div>
  );
}
