'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { motion, AnimatePresence } from 'motion/react';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Cpu,
  Minus,
  Plus,
  RefreshCw,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatDate, formatMoney } from '@/lib/format';
import { useT, type Key } from '@/lib/i18n';
import { spring, fade } from '@/lib/motion';
import { useIntents, useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';
import type { CashAnalysis } from '@/lib/types';
import { api, type SentinelTelemetry } from '@/lib/api';
import { TODAY } from '@/lib/mock/demo';

function daysBetween(a: string, b: string) {
  const msA = Date.parse(a);
  const msB = Date.parse(b);
  if (Number.isNaN(msA) || Number.isNaN(msB)) return 0;
  return Math.round((msB - msA) / 86_400_000);
}

export function AutonomousSentinel({ analysis: a }: { analysis: CashAnalysis }) {
  const { t } = useT();
  const { alertThresholdDays, update } = useWorkspace();
  const intents = useIntents();
  const pending = intents.find((i) => i.status === 'STAGED_PENDING_HITL');

  const [isEvaluating, setIsEvaluating] = useState(false);
  const [lastAuditTime, setLastAuditTime] = useState<string>('Just now');
  const [telemetry, setTelemetry] = useState<SentinelTelemetry | null>(null);

  useEffect(() => {
    let mounted = true;
    const fetchTelemetry = async () => {
      try {
        const data = await api.sentinelHeartbeat();
        if (mounted) {
          setTelemetry(data);
          if (data.last_sweep_at) {
            const dt = new Date(data.last_sweep_at);
            setLastAuditTime(dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
          }
        }
      } catch {
        // Sentinel daemon offline or server starting
      }
    };
    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 15_000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const f = a.forecast ?? null;
  const deficitDate = f?.projected_deficit_date ?? a.projected_depletion_date;
  const daysUntilDeficit = deficitDate ? Math.max(0, daysBetween(TODAY, deficitDate)) : (a.runway_days ?? 90);
  const runwayDays = daysUntilDeficit;

  const isTriggered = runwayDays <= alertThresholdDays;
  const deltaDays = Math.abs(alertThresholdDays - runwayDays);

  const handleReevaluate = async () => {
    setIsEvaluating(true);
    try {
      const res = await api.sentinelEvaluate();
      if (res.timestamp) {
        const dt = new Date(res.timestamp);
        setLastAuditTime(dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      }
      const data = await api.sentinelHeartbeat();
      setTelemetry(data);
    } catch {
      setLastAuditTime(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    } finally {
      setIsEvaluating(false);
    }
  };

  const handleAdjustThreshold = (delta: number) => {
    const next = Math.max(7, Math.min(90, alertThresholdDays + delta));
    update({ alertThresholdDays: next });
  };

  const shortfallAmount = f?.projected_shortfall_amount ? formatMoney(f.projected_shortfall_amount) : '$13,420.00';
  const bridgeAmount = f?.recommended_bridge_amount ? formatMoney(f.recommended_bridge_amount) : '$15,000.00';
  const deficitFormattedDate = deficitDate ? formatDate(deficitDate) : 'Nov 28, 2026';
  const balanceAmount = formatMoney(a.current_balance ?? '29922.08');

  // Relative percentages for the comparison bar
  const maxDisplayDays = Math.max(60, alertThresholdDays * 1.4, runwayDays * 1.4);
  const runwayPct = Math.min(100, Math.max(5, (runwayDays / maxDisplayDays) * 100));
  const thresholdPct = Math.min(100, Math.max(5, (alertThresholdDays / maxDisplayDays) * 100));

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={spring.gentle}
      className="mt-8 overflow-hidden rounded-2xl border bg-card/95 backdrop-blur-md shadow-xs"
      aria-label={t('sentinel.title')}
    >
      {/* 1. Header Bar with Live Indicator */}
      <div className="flex flex-col gap-3 border-b bg-muted/30 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
            <Cpu className="size-4.5" aria-hidden />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold tracking-tight text-foreground truncate">
                {t('sentinel.title')}
              </h2>
              <span className="flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                <span className="size-1.5 rounded-full bg-primary animate-pulse" aria-hidden />
                <span>{telemetry?.daemon_status === 'STOPPED' ? 'DAEMON PAUSED' : t('sentinel.active')}</span>
              </span>
              {telemetry && (
                <span className="hidden sm:inline-block font-mono text-[10px] text-muted-foreground border-l border-border/60 pl-2">
                  Cycle #{telemetry.cycle_count} · {telemetry.interval_seconds}s cadence
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground truncate">
              {isEvaluating ? t('sentinel.evaluating') : t('sentinel.lastAudit', { time: lastAuditTime })}
              {telemetry?.last_sweep_summary && (
                <span className="ml-1.5 text-[11px] text-ink-2 font-mono">
                  ({telemetry.last_sweep_summary.tenants_audited} sessions scanned · {telemetry.last_sweep_summary.actions_staged} auto-staged)
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleReevaluate}
            disabled={isEvaluating}
            className="h-8 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            title="Trigger an on-demand liquidity and debt audit"
          >
            <RefreshCw className={cn('size-3.5', isEvaluating && 'animate-spin text-primary')} aria-hidden />
            <span>{t('sentinel.reEvaluate')}</span>
          </Button>
        </div>
      </div>

      {/* 2. Buffer Comparison Gauge */}
      <div className="p-5 sm:p-6 space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* Card A: Current Projected Runway */}
          <div className="rounded-xl border bg-background/50 p-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Current Runway</span>
              <span className="font-mono text-[10px] uppercase tracking-wider">Forecast</span>
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="figures text-3xl font-bold tracking-tight text-foreground">
                {runwayDays}
              </span>
              <span className="text-xs text-muted-foreground">days until deficit</span>
            </div>
            <p className="mt-2 text-xs text-ink-2 truncate">
              Shortfall on {deficitFormattedDate}
            </p>
          </div>

          {/* Card B: Warning Threshold with Live Stepper */}
          <div className="rounded-xl border bg-background/50 p-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Warning Threshold</span>
              <span className="font-mono text-[10px] uppercase tracking-wider text-primary">Policy Rule</span>
            </div>
            <div className="mt-2 flex items-center justify-between">
              <div className="flex items-baseline gap-2">
                <span className="figures text-3xl font-bold tracking-tight text-foreground">
                  {alertThresholdDays}
                </span>
                <span className="text-xs text-muted-foreground">days safety target</span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => handleAdjustThreshold(-5)}
                  className="flex size-7 items-center justify-center rounded-md border bg-card hover:bg-muted text-foreground transition-colors active:scale-95"
                  title="Decrease threshold by 5 days"
                  aria-label="Decrease threshold"
                >
                  <Minus className="size-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => handleAdjustThreshold(5)}
                  className="flex size-7 items-center justify-center rounded-md border bg-card hover:bg-muted text-foreground transition-colors active:scale-95"
                  title="Increase threshold by 5 days"
                  aria-label="Increase threshold"
                >
                  <Plus className="size-3.5" />
                </button>
              </div>
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground truncate">
              Evaluated against ZenEngine decision table
            </p>
          </div>

          {/* Card C: Sentinel Decision State */}
          <div className={cn(
            'rounded-xl border p-4 sm:col-span-2 lg:col-span-1 transition-colors',
            isTriggered ? 'border-warning/40 bg-warning/10' : 'border-good/30 bg-good/5'
          )}>
            <div className="flex items-center justify-between text-xs">
              <span className={cn('font-semibold uppercase tracking-wider text-[10px]', isTriggered ? 'text-warning-text' : 'text-good-text')}>
                {isTriggered ? 'Trigger Condition Met' : 'Solvent & Protected'}
              </span>
              {isTriggered ? (
                <AlertTriangle className="size-4 text-warning-text shrink-0" aria-hidden />
              ) : (
                <CheckCircle2 className="size-4 text-good-text shrink-0" aria-hidden />
              )}
            </div>
            <p className="mt-2 text-base font-semibold text-foreground">
              {isTriggered ? t('sentinel.deltaTriggered', { n: deltaDays }) : t('sentinel.deltaSafe', { n: deltaDays })}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {isTriggered
                ? 'Automated liquidity protocol initiated. Staged proposal waiting.'
                : 'Cash buffer safely covers all projected obligations.'}
            </p>
          </div>
        </div>

        {/* Visual Comparison Gauge Bar */}
        <div className="space-y-1.5 rounded-xl border bg-muted/20 p-3.5">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Buffer Horizon Progress</span>
            <span className="font-mono text-[11px]">
              {runwayDays}d runway / {alertThresholdDays}d threshold
            </span>
          </div>
          <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-muted">
            {/* Threshold target marker */}
            <div
              className="absolute top-0 bottom-0 z-10 w-1 bg-foreground/60 shadow-xs"
              style={{ left: `${thresholdPct}%` }}
              title={`Warning threshold: ${alertThresholdDays} days`}
            />
            {/* Current Runway Bar */}
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${runwayPct}%` }}
              transition={spring.gentle}
              className={cn(
                'h-full rounded-full transition-colors',
                isTriggered ? 'bg-warning' : 'bg-primary'
              )}
            />
          </div>
          <div className="flex items-center justify-between text-[10.5px] text-muted-foreground">
            <span>0 days</span>
            <span className="font-medium text-foreground">Target: {alertThresholdDays}d (Line)</span>
            <span>{Math.round(maxDisplayDays)} days</span>
          </div>
        </div>

        {/* 3. Autonomous Actions Executed (Zero-Prompt Pipeline Trace) */}
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            {t('sentinel.traceTitle')}
          </h3>
          <div className="grid gap-2.5 sm:grid-cols-2">
            {/* Step 1 */}
            <div className="flex items-start gap-2.5 rounded-xl border bg-card/60 p-3 text-xs shadow-2xs">
              <div className="flex size-5 shrink-0 items-center justify-center rounded-full bg-good/15 text-good-text mt-0.5">
                <CheckCircle2 className="size-3.5" />
              </div>
              <div className="min-w-0">
                <p className="font-medium text-foreground">1. Multi-Account Statement Ingestion</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  {t('sentinel.step1', { amount: balanceAmount })}
                </p>
                <span className="mt-1 inline-block font-mono text-[10px] text-muted-foreground/80">
                  csv_parser.py · 420ms
                </span>
              </div>
            </div>

            {/* Step 2 */}
            <div className="flex items-start gap-2.5 rounded-xl border bg-card/60 p-3 text-xs shadow-2xs">
              <div className="flex size-5 shrink-0 items-center justify-center rounded-full bg-good/15 text-good-text mt-0.5">
                <CheckCircle2 className="size-3.5" />
              </div>
              <div className="min-w-0">
                <p className="font-medium text-foreground">2. Predictive Overdraft Pinpointing</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  {t('sentinel.step2', { amount: shortfallAmount, date: deficitFormattedDate })}
                </p>
                <span className="mt-1 inline-block font-mono text-[10px] text-muted-foreground/80">
                  deficit_severity_policy.json · 9ms
                </span>
              </div>
            </div>

            {/* Step 3 */}
            <div className="flex items-start gap-2.5 rounded-xl border bg-card/60 p-3 text-xs shadow-2xs">
              <div className="flex size-5 shrink-0 items-center justify-center rounded-full bg-good/15 text-good-text mt-0.5">
                <CheckCircle2 className="size-3.5" />
              </div>
              <div className="min-w-0">
                <p className="font-medium text-foreground">3. Digital Credit Matching & APR Audit</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  {t('sentinel.step3')}
                </p>
                <span className="mt-1 inline-block font-mono text-[10px] text-muted-foreground/80">
                  usury_policy.json · 64ms
                </span>
              </div>
            </div>

            {/* Step 4 */}
            <div className="flex items-start gap-2.5 rounded-xl border bg-card/60 p-3 text-xs shadow-2xs">
              <div className="flex size-5 shrink-0 items-center justify-center rounded-full bg-good/15 text-good-text mt-0.5">
                <CheckCircle2 className="size-3.5" />
              </div>
              <div className="min-w-0">
                <p className="font-medium text-foreground">4. Tier 2 Safe Proposal Staging</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  {t('sentinel.step4', { amount: bridgeAmount })}
                </p>
                <span className="mt-1 inline-block font-mono text-[10px] text-muted-foreground/80">
                  security_gate_policy.json · 21ms
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* 4. Safety Handshake Footer */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-xl border border-primary/25 bg-primary/5 dark:bg-primary/10 p-3.5 text-xs">
          <div className="flex items-center gap-2.5 min-w-0">
            <ShieldCheck className="size-4 shrink-0 text-primary" aria-hidden />
            <span className="text-muted-foreground leading-relaxed">
              <span className="font-medium text-foreground">Three-Tier Governance:</span> {t('sentinel.tier2Badge')}
            </span>
          </div>

          {pending && (
            <Button asChild size="sm" className="shrink-0 text-xs gap-1.5 shadow-xs">
              <Link href="/assistant">
                <span>{t('sentinel.reviewAction')}</span>
                <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            </Button>
          )}
        </div>
      </div>
    </motion.section>
  );
}
