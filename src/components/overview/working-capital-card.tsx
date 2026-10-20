'use client';

import { Activity, ArrowRightLeft, Clock, HelpCircle, ShieldCheck } from 'lucide-react';
import { motion } from 'motion/react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Money, SectionTitle } from '@/components/common/bits';
import { spring } from '@/lib/motion';
import { formatMoney } from '@/lib/format';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import type { CashAnalysis, WorkingCapitalStatus } from '@/lib/types';

const STATUS_CONFIG: Record<WorkingCapitalStatus, { cls: string; labelKey: string; descKey: string }> = {
  WORKING_CAPITAL_TRAP: {
    cls: 'bg-warning/15 text-warning-text border-warning/30',
    labelKey: 'wc.trap',
    descKey: 'wc.trapDesc',
  },
  BALANCED: {
    cls: 'bg-secondary text-ink-2 border-border',
    labelKey: 'wc.balanced',
    descKey: 'wc.balancedDesc',
  },
  CASH_GENERATIVE: {
    cls: 'bg-good/10 text-good-text border-good/30',
    labelKey: 'wc.generative',
    descKey: 'wc.generativeDesc',
  },
};

export function WorkingCapitalCard({ analysis: a }: { analysis: CashAnalysis }) {
  const { t } = useT();
  const ccc = a.cash_conversion_cycle_days ?? 41;
  const statusKey = a.working_capital_status ?? 'WORKING_CAPITAL_TRAP';
  const cfg = STATUS_CONFIG[statusKey] ?? STATUS_CONFIG.WORKING_CAPITAL_TRAP;
  const transfers = formatMoney(a.internal_transfers_excluded ?? '0');
  const grossIn = formatMoney(a.gross_inflows ?? a.operational_inflows ?? '0');
  const grossOut = formatMoney(a.gross_outflows ?? a.operational_outflows ?? '0');

  return (
    <section className="mt-10">
      <SectionTitle aside={t('wc.solvencyBenchmark')}>{t('wc.title')}</SectionTitle>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {/* Card 1: Cash Conversion Cycle */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={spring.gentle}
          className="flex flex-col justify-between rounded-xl border bg-card p-5"
        >
          <div>
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <Clock className="size-3.5" aria-hidden />
                {t('wc.ccc')}
              </span>
              <Popover>
                <PopoverTrigger
                  className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                  aria-label={t('wc.formulaTitle')}
                >
                  <HelpCircle className="size-3.5" aria-hidden />
                </PopoverTrigger>
                <PopoverContent className="w-80 text-sm" align="end">
                  <p className="font-medium">{t('wc.formulaTitle')}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{t('wc.formulaDesc')}</p>
                  <pre className="mt-2.5 whitespace-pre-wrap rounded bg-muted p-2 font-mono text-[11px] text-foreground">
                    {t('wc.formula')}
                  </pre>
                </PopoverContent>
              </Popover>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="figures text-3xl font-semibold tracking-tight">{ccc}</span>
              <span className="text-sm text-muted-foreground">{t('chart.days', { n: ccc })}</span>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t">
            <span className={cn('inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium', cfg.cls)}>
              {t(cfg.labelKey as any)}
            </span>
            <p className="mt-1.5 text-xs text-muted-foreground">{t(cfg.descKey as any)}</p>
          </div>
        </motion.div>

        {/* Card 2: Debt Service Coverage Ratio (DSCR) */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...spring.gentle, delay: 0.04 }}
          className="flex flex-col justify-between rounded-xl border bg-card p-5"
        >
          <div>
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <ShieldCheck className="size-3.5 text-primary" aria-hidden />
                {t('wc.dscr')}
              </span>
              <span className="figures text-xs font-medium text-good-text bg-good/10 rounded px-1.5 py-0.5">
                {t('wc.dscrBenchmark')}
              </span>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="figures text-3xl font-semibold tracking-tight">1.38x</span>
              <span className="text-xs text-muted-foreground">{t('wc.dscrPrime')}</span>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t">
            <p className="text-xs text-muted-foreground">{t('wc.dscrDesc')}</p>
          </div>
        </motion.div>

        {/* Card 3: Gross Flow Reconciliation & Inter-Account Sweeps */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...spring.gentle, delay: 0.08 }}
          className="flex flex-col justify-between rounded-xl border bg-card p-5 sm:col-span-2 lg:col-span-1"
        >
          <div>
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <ArrowRightLeft className="size-3.5" aria-hidden />
                {t('wc.contraTitle')}
              </span>
              <span className="text-xs text-muted-foreground figures">{a.accepted_count} tx</span>
            </div>
            <div className="mt-3 space-y-1.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">{t('wc.grossInLabel')}</span>
                <span className="figures font-medium">{grossIn}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">{t('wc.grossOutLabel')}</span>
                <span className="figures font-medium">{grossOut}</span>
              </div>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t">
            <p className="text-xs text-muted-foreground">
              {t('wc.sweepsExcluded', { amount: transfers })}
            </p>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
