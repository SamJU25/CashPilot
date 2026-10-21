'use client';

import Link from 'next/link';
import { motion } from 'motion/react';
import { AlertOctagon, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Money, PageHeader, SectionTitle } from '@/components/common/bits';
import { ScoreRing } from '@/components/charts/kit';
import { UnderwritingDossierDialog } from '@/components/funding/underwriting-dossier-dialog';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/common/states';
import { centsToString, formatDate, formatMoney, stringToCents } from '@/lib/format';
import { BASE, COMPARE_DAYS, DOSSIER, OPTIONS, costToBorrow } from '@/lib/mock/demo';
import { spring } from '@/lib/motion';
import { useData } from '@/lib/use-data';
import { useIntents, useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';
import type { FinancingOption, Forecast } from '@/lib/types';
import { useT, type Key } from '@/lib/i18n';

function ScoreScale({ score }: { score: number }) {
  const { t } = useT();
  return (
    <div>
      <div className="relative">
        <div className="flex h-1.5 gap-0.5 overflow-hidden rounded-full">
          <span className="w-[40%] bg-critical/40" />
          <span className="w-[30%] bg-warning/50" />
          <span className="w-[30%] bg-good/50" />
        </div>
        <motion.span
          className="absolute -top-1 h-3.5 w-0.5 rounded bg-foreground"
          style={{ left: `${score}%` }}
          initial={{ opacity: 0, scaleY: 0.4 }}
          animate={{ opacity: 1, scaleY: 1 }}
          transition={spring.gentle}
          aria-hidden
        />
      </div>
      <div className="mt-2 grid grid-cols-[40%_30%_30%] text-xs text-muted-foreground">
        <span>{t('scale.high')}</span>
        <span>{t('scale.cond')}</span>
        <span>{t('scale.prime')}</span>
      </div>
    </div>
  );
}

const PREDATORY_APR = 36;

/** True APR on a scale shared by every offer, with the predatory line marked. */
function AprMeter({ apr, max, predatory }: { apr: number; max: number; predatory: boolean }) {
  return (
    <div className="relative mt-2 h-1.5 w-full max-w-[11rem] rounded-full bg-muted" aria-hidden>
      <motion.div
        className={cn('absolute inset-y-0 left-0 rounded-full', predatory ? 'bg-critical' : 'bg-ink-2/70')}
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        style={{ width: `${Math.min(100, (apr / max) * 100)}%`, originX: 0 }}
        transition={spring.gentle}
      />
      <span className="absolute -inset-y-1 w-px bg-foreground/70" style={{ left: `${(PREDATORY_APR / max) * 100}%` }} />
    </div>
  );
}

function useQuote(o: FinancingOption, sample: boolean) {
  const { t } = useT();
  // The lender's own wording is translated for the sample offers; live offers carry it as quoted_as.
  const quoteIndex = sample ? OPTIONS.findIndex((x) => x.provider === o.provider) : -1;
  return quoteIndex >= 0 ? t(`quote.${quoteIndex}` as Key) : (o.quoted_as ?? null);
}

function Stat({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="mt-1">{children}</div>
    </div>
  );
}

const fitTone = (n: number) => (n >= 75 ? 'text-good' : n >= 50 ? 'text-warning' : 'text-critical');

/** The offer that fits best, with its numbers side by side and the next step on it. */
function BestOffer({ o, needCents, drafted, sample, aprMax }: { o: FinancingOption; needCents: number; drafted: boolean; sample: boolean; aprMax: number }) {
  const { t } = useT();
  const quote = useQuote(o, sample);
  return (
    <article className="rounded-xl border border-primary/40 bg-card p-6 shadow-[0_0_0_4px_rgb(var(--primary)/0.06)] sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <span className="rounded-full bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground">{t('fund.best')}</span>
          <h3 className="mt-2 font-display text-2xl font-semibold tracking-tight">{o.provider}</h3>
          <p className="text-sm text-muted-foreground">{t('fund.offerMeta', { product: t(`product.${o.product_type}` as Key), amount: formatMoney(o.max_amount, undefined, { cents: false }), days: o.term_days })}</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-xs text-muted-foreground">{t('fund.fitLabel')}</p>
            <p className="text-xs text-ink-2">{t('fund.fitOutOf')}</p>
          </div>
          <ScoreRing value={o.suitability_score} tone={fitTone(o.suitability_score)} size={52} label={t('fund.fit', { n: o.suitability_score })} />
        </div>
      </div>

      <div className="mt-6 grid gap-6 border-t pt-6 sm:grid-cols-3">
        <Stat label={t('fund.colApr')}>
          <p className="figures font-display text-4xl font-semibold leading-none tracking-tight">{o.apr_percent}%</p>
          <AprMeter apr={Number(o.apr_percent)} max={aprMax} predatory={false} />
        </Stat>
        <Stat label={t('fund.costFor', { days: COMPARE_DAYS })}>
          <Money value={centsToString(costToBorrow(needCents, o.apr_percent))} className="font-display text-4xl font-semibold leading-none tracking-tight" />
        </Stat>
        <Stat label={t('fund.colLimit')}>
          <Money value={o.max_amount} cents={false} className="font-display text-4xl font-semibold leading-none tracking-tight" />
        </Stat>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
        <p className="max-w-xl text-sm text-muted-foreground">{quote ? t('fund.theyQuote', { quote }) : t('lv.trueApr')}</p>
        {drafted && (
          <Button asChild>
            <Link href="/assistant">{t('fund.review')}</Link>
          </Button>
        )}
      </div>
    </article>
  );
}

function OfferCard({ o, needCents, drafted, sample, aprMax }: { o: FinancingOption; needCents: number; drafted: boolean; sample: boolean; aprMax: number }) {
  const { t } = useT();
  const quote = useQuote(o, sample);
  return (
    <article className="flex flex-col rounded-xl border bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-medium">{o.provider}</h3>
          <p className="text-sm text-muted-foreground">{t(`product.${o.product_type}` as Key)}</p>
        </div>
        <ScoreRing value={o.suitability_score} tone={fitTone(o.suitability_score)} label={t('fund.fit', { n: o.suitability_score })} />
      </div>
      <div className="mt-5 grid grid-cols-2 gap-4">
        <Stat label={t('fund.colApr')}>
          <p className="figures font-display text-2xl font-semibold leading-none">{o.apr_percent}%</p>
          <AprMeter apr={Number(o.apr_percent)} max={aprMax} predatory={false} />
        </Stat>
        <Stat label={t('fund.costFor', { days: COMPARE_DAYS })}>
          <Money value={centsToString(costToBorrow(needCents, o.apr_percent))} className="font-display text-2xl font-semibold leading-none" />
        </Stat>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">{t('fund.offerMeta', { product: t(`product.${o.product_type}` as Key), amount: formatMoney(o.max_amount, undefined, { cents: false }), days: o.term_days })}</p>
      {quote && <p className="mt-1 text-xs text-muted-foreground">{t('fund.theyQuote', { quote })}</p>}
      {drafted && (
        <Button asChild size="sm" className="mt-4 self-start">
          <Link href="/assistant">{t('fund.review')}</Link>
        </Button>
      )}
    </article>
  );
}

/** Kept out of the ranking: shown so the owner recognises the pattern if this lender calls. */
function PredatoryOffer({ o, needCents, sample, aprMax }: { o: FinancingOption; needCents: number; sample: boolean; aprMax: number }) {
  const { t } = useT();
  const quote = useQuote(o, sample);
  return (
    <article className="grid gap-5 rounded-xl border border-critical/40 bg-critical/5 p-5 md:grid-cols-[minmax(0,1.4fr)_1fr_1fr] md:items-center">
      <div>
        <p className="flex items-center gap-1.5 text-sm font-medium text-critical-text">
          <AlertOctagon className="size-4 shrink-0" aria-hidden />
          {t('fund.avoid')}
        </p>
        <h3 className="mt-1 font-medium">{o.provider}</h3>
        <p className="text-sm text-muted-foreground">{t('fund.predatory')}</p>
      </div>
      <Stat label={t('fund.colApr')}>
        <p className="figures font-display text-2xl font-semibold leading-none text-critical-text">{o.apr_percent}%</p>
        <AprMeter apr={Number(o.apr_percent)} max={aprMax} predatory />
        {quote && <p className="mt-2 text-xs text-muted-foreground">{t('fund.theyQuote', { quote })}</p>}
      </Stat>
      <Stat label={t('fund.costFor', { days: COMPARE_DAYS })}>
        <Money value={centsToString(costToBorrow(needCents, o.apr_percent))} className="font-display text-2xl font-semibold leading-none" />
      </Stat>
    </article>
  );
}

export default function FundingPage() {
  const state = useData<{ dossier: typeof DOSSIER; options: FinancingOption[]; forecast: Forecast | null }>(
    () => ({ dossier: DOSSIER, options: OPTIONS, forecast: BASE.forecast }),
    // Connect the live analysis forecast so the bridge amount and shortfall date display for live data.
    (live) => live.underwrite && { ...live.underwrite, forecast: live.analysis?.forecast ?? null },
  );
  const { source, live } = useWorkspace();
  const intents = useIntents();
  const { t } = useT();
  const header = (
    <PageHeader
      title={t('nav.funding')}
      description={t('fund.desc')}
      actions={state.status === 'ready' ? <UnderwritingDossierDialog dossier={state.data.dossier} options={state.data.options} forecast={state.data.forecast} /> : null}
    />
  );

  if (state.status === 'loading') return <>{header}<LoadingBlock rows={4} /></>;
  if (state.status === 'error') return <>{header}<ErrorState message={state.message} retry={state.retry} /></>;
  if (state.status === 'empty')
    return (
      <>
        {header}
        {source === 'live' && live.analysis?.document_format === 'MANUAL' ? (
          <EmptyState title={t('fund.typedTitle')} body={t('fund.typedBody')} />
        ) : (
          <EmptyState title={t('fund.emptyTitle')} body={t('fund.emptyBody')} />
        )}
      </>
    );

  const { dossier: d, options, forecast: f } = state.data;
  // Offers are costed on the bridge the forecast asks for, or on the most the business qualifies for.
  const needCents = stringToCents(f?.recommended_bridge_amount ?? d.max_qualified_limit);
  const drafted = intents.find((i) => i.status === 'STAGED_PENDING_HITL')?.target_identifier;
  const sorted = [...options].sort((a, b) => Number(a.is_predatory) - Number(b.is_predatory) || b.suitability_score - a.suitability_score);
  const sample = source === 'sample';
  const fair = sorted.filter((o) => !o.is_predatory);
  const [best, ...others] = fair;
  const predatory = sorted.filter((o) => o.is_predatory);
  const aprMax = Math.max(PREDATORY_APR * 2, ...options.map((o) => Number(o.apr_percent) * 1.1));

  return (
    <div>
      {header}

      <section className="overflow-hidden rounded-xl border bg-card">
        <div className="grid gap-8 p-6 sm:p-8 lg:grid-cols-3">
          {f?.projected_deficit_date ? (
            <div>
              <p className="text-sm text-muted-foreground">{t('fund.need')}</p>
              <Money value={f.recommended_bridge_amount} className="mt-1 block font-display text-[2.5rem] font-semibold leading-none tracking-tight" />
              <p className="mt-2 text-sm text-ink-2">{t('fund.needNote', { date: formatDate(f.projected_deficit_date) })}</p>
            </div>
          ) : null}
          <div>
            <p className="text-sm text-muted-foreground">{t('fund.max')}</p>
            <Money value={d.max_qualified_limit} className="mt-1 block font-display text-[2.5rem] font-semibold leading-none tracking-tight" />
            {/* The backend's proposal is English only; the sample company's is translated. */}
            <p className="mt-2 max-w-sm text-sm text-ink-2">{source === 'sample' ? t('fund.proposal', { amount: formatMoney(d.max_qualified_limit) }) : d.conditional_proposal}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">{t('fund.score')}</p>
            <p className="mt-1 flex items-baseline gap-2">
              <span className="figures font-display text-[2.5rem] font-semibold leading-none tracking-tight">{d.liquidity_score}</span>
              <span className="text-sm text-muted-foreground">{t('fund.outOf', { tier: t(`risk.${d.risk_tier}` as Key) })}</span>
            </p>
            <div className="mt-4 max-w-xs">
              <ScoreScale score={d.liquidity_score ?? 0} />
            </div>
          </div>
        </div>
        <dl className="grid grid-cols-1 gap-4 border-t bg-muted/30 px-6 py-4 text-sm sm:grid-cols-3 sm:px-8">
          <div className="flex items-baseline justify-between gap-3 sm:block">
            <dt className="text-muted-foreground">{t('fund.dab')}</dt>
            <dd className="font-medium sm:mt-0.5">
              <Money value={d.daily_average_balance} />
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-3 sm:block">
            <dt className="text-muted-foreground">{t('fund.steady')}</dt>
            <dd className="font-medium sm:mt-0.5">{t(source === 'sample' ? 'fund.steadyVal' : 'lv.varies', { pct: Math.round(Number(d.revenue_volatility_cv) * 100) })}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-3 sm:block">
            <dt className="text-muted-foreground">{t('fund.nsf')}</dt>
            <dd className="figures font-medium sm:mt-0.5">{d.nsf_count}</dd>
          </div>
        </dl>
      </section>

      <section className="mt-10">
        <SectionTitle aside={t('fund.costBasis', { amount: formatMoney(centsToString(needCents), undefined, { cents: false }), days: COMPARE_DAYS })}>
          {t('fund.offers')}
        </SectionTitle>
        <div className="space-y-4">
          {best && <BestOffer o={best} needCents={needCents} drafted={best.provider === drafted} sample={sample} aprMax={aprMax} />}
          {others.length > 0 && (
            <div className={cn("grid gap-4 md:grid-cols-2", others.length >= 3 && "xl:grid-cols-3")}>
              {others.map((o) => (
                <OfferCard key={o.provider} o={o} needCents={needCents} drafted={o.provider === drafted} sample={sample} aprMax={aprMax} />
              ))}
            </div>
          )}
          {predatory.map((o) => (
            <PredatoryOffer key={o.provider} o={o} needCents={needCents} sample={sample} aprMax={aprMax} />
          ))}
        </div>
        <p className="mt-4 flex max-w-2xl items-start gap-2 text-sm text-muted-foreground">
          <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            {t('fund.footer')} {t('fund.meterNote', { n: PREDATORY_APR })}
          </span>
        </p>
      </section>
    </div>
  );
}
