'use client';

import Link from 'next/link';
import { motion } from 'motion/react';
import { AlertOctagon, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Money, PageHeader, SectionTitle } from '@/components/common/bits';
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
        <div className="flex h-2 gap-0.5 overflow-hidden rounded-full">
          <span className="w-[40%] bg-critical/40" />
          <span className="w-[30%] bg-warning/50" />
          <span className="w-[30%] bg-good/50" />
        </div>
        <motion.span
          className="absolute -top-1 h-4 w-0.5 rounded bg-foreground"
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

function OfferRow({ o, needCents, drafted, sample }: { o: FinancingOption; needCents: number; drafted: boolean; sample: boolean }) {
  const cost = costToBorrow(needCents, o.apr_percent);
  const { t } = useT();
  // The lender's own wording is translated for the sample offers; live offers carry it as quoted_as.
  const quoteIndex = sample ? OPTIONS.findIndex((x) => x.provider === o.provider) : -1;
  return (
    <li className={cn('grid gap-4 py-5 md:grid-cols-[1.4fr_1fr_1fr_auto] md:items-center', o.is_predatory && 'relative before:absolute before:inset-y-4 before:-left-3 before:w-0.5 before:rounded before:bg-critical')}>
      <div>
        <p className="font-medium">{o.provider}</p>
        <p className="text-sm text-muted-foreground">
          {t('fund.offerMeta', { product: t(`product.${o.product_type}` as Key), amount: formatMoney(o.max_amount, undefined, { cents: false }), days: o.term_days })}
        </p>
        {o.is_predatory && (
          <p className="mt-2 flex items-start gap-1.5 text-sm text-critical-text">
            <AlertOctagon className="mt-0.5 size-4 shrink-0" aria-hidden />
            {t('fund.predatory')}
          </p>
        )}
      </div>
      <div>
        <p className={cn('figures text-2xl font-semibold tracking-tight', o.is_predatory && 'text-critical-text')}>{o.apr_percent}%</p>
        <p className="text-xs text-muted-foreground">
          {quoteIndex >= 0 || o.quoted_as ? t('fund.trueApr', { quote: quoteIndex >= 0 ? t(`quote.${quoteIndex}` as Key) : o.quoted_as! }) : t('lv.trueApr')}
        </p>
      </div>
      <div>
        <Money value={centsToString(cost)} className="text-base font-medium" />
        <p className="text-xs text-muted-foreground">{t('fund.cost', { amount: formatMoney(centsToString(needCents), undefined, { cents: false }), days: COMPARE_DAYS })}</p>
      </div>
      <div className="md:text-right">
        {drafted ? (
          <Button asChild size="sm">
            <Link href="/assistant">{t('fund.review')}</Link>
          </Button>
        ) : (
          <span className="text-sm text-muted-foreground">{t('fund.fit', { n: o.suitability_score })}</span>
        )}
      </div>
    </li>
  );
}

export default function FundingPage() {
  const state = useData<{ dossier: typeof DOSSIER; options: FinancingOption[]; forecast: Forecast | null }>(
    () => ({ dossier: DOSSIER, options: OPTIONS, forecast: BASE.forecast }),
    // shortcut: no forecast until /analyze returns one (handoff item 1), so the bridge amount is not shown for live data.
    (live) => live.underwrite && { ...live.underwrite, forecast: null },
  );
  const { source, live } = useWorkspace();
  const intents = useIntents();
  const { t } = useT();
  const header = (
    <PageHeader
      title={t('nav.funding')}
      description={t('fund.desc')}
      actions={
        state.status === 'ready' ? (
          <UnderwritingDossierDialog
            dossier={state.data.dossier}
            options={state.data.options}
            forecast={state.data.forecast}
          />
        ) : null
      }
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

  return (
    <div>
      {header}
      <section className="grid gap-10 rounded-xl border bg-card p-6 lg:grid-cols-[1.2fr_1fr]">
        <div>
          <p className="text-sm text-muted-foreground">{t('fund.score')}</p>
          <p className="mt-1 flex items-baseline gap-2">
            <span className="figures text-4xl font-semibold tracking-tight">{d.liquidity_score}</span>
            <span className="text-sm text-muted-foreground">{t('fund.outOf', { tier: t(`risk.${d.risk_tier}` as Key) })}</span>
          </p>
          <div className="mt-5 max-w-md">
            <ScoreScale score={d.liquidity_score ?? 0} />
          </div>
          {/* The backend's proposal is English only; the sample company's is translated. */}
          <p className="mt-5 max-w-lg text-sm text-ink-2">{source === 'sample' ? t('fund.proposal', { amount: formatMoney(d.max_qualified_limit) }) : d.conditional_proposal}</p>
        </div>
        <dl className="grid grid-cols-2 content-start gap-x-6 gap-y-5 text-sm">
          {f?.projected_deficit_date && (
            <div>
              <dt className="text-muted-foreground">{t('fund.need')}</dt>
              <dd className="mt-0.5 text-lg font-semibold">
                <Money value={f.recommended_bridge_amount} />
              </dd>
              <dd className="text-xs text-muted-foreground">{t('fund.needNote', { date: formatDate(f.projected_deficit_date) })}</dd>
            </div>
          )}
          <div>
            <dt className="text-muted-foreground">{t('fund.max')}</dt>
            <dd className="mt-0.5 text-lg font-semibold">
              <Money value={d.max_qualified_limit} />
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{t('fund.dab')}</dt>
            <dd className="mt-0.5">
              <Money value={d.daily_average_balance} />
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{t('fund.steady')}</dt>
            <dd className="mt-0.5">{t(source === 'sample' ? 'fund.steadyVal' : 'lv.varies', { pct: Math.round(Number(d.revenue_volatility_cv) * 100) })}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{t('fund.nsf')}</dt>
            <dd className="mt-0.5 figures">{d.nsf_count}</dd>
          </div>
        </dl>
      </section>

      <section className="mt-12">
        <SectionTitle aside={t('count.offers', { n: options.length })}>{t('fund.offers')}</SectionTitle>
        <ul className="divide-y border-y">
          {sorted.map((o) => (
            <OfferRow key={o.provider} o={o} needCents={needCents} drafted={o.provider === drafted} sample={source === 'sample'} />
          ))}
        </ul>
        <p className="mt-4 flex max-w-2xl items-start gap-2 text-sm text-muted-foreground">
          <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
          {t('fund.footer')}
        </p>
      </section>
    </div>
  );
}
