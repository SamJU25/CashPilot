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

function addDays(baseDate: string, days: number): string {
  const ms = Date.parse(baseDate.includes('T') ? baseDate : `${baseDate}T00:00:00Z`);
  if (Number.isNaN(ms)) return '';
  const d = new Date(ms + days * 86_400_000);
  return d.toISOString().split('T')[0];
}

export function AutonomousSentinel({ analysis: a }: { analysis: CashAnalysis }) {
  const { t } = useT();
  const { alertThresholdDays, update } = useWorkspace();
  const intents = useIntents();
  const pending = intents.find((i) => i.status === 'STAGED_PENDING_HITL');

  const [isEvaluating, setIsEvaluating] = useState(false);
  const [lastAuditTime, setLastAuditTime] = useState<string>('Just now');
  const [telemetry, setTelemetry] = useState<SentinelTelemetry | null>(null);
  const [thresholdInput, setThresholdInput] = useState(String(alertThresholdDays));

  useEffect(() => {
    setThresholdInput(String(alertThresholdDays));
  }, [alertThresholdDays]);

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

  // Automatically re-evaluate and sync background telemetry whenever threshold changes
  useEffect(() => {
    const timer = setTimeout(() => {
      setIsEvaluating(true);
      api.sentinelEvaluate()
        .then((res) => {
          if (res.timestamp) {
            const dt = new Date(res.timestamp);
            setLastAuditTime(dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
          }
          return api.sentinelHeartbeat();
        })
        .then((data) => {
          if (data) setTelemetry(data);
        })
        .catch(() => {})
        .finally(() => setIsEvaluating(false));
    }, 400);
    return () => clearTimeout(timer);
  }, [alertThresholdDays]);

  const handleAdjustThreshold = (delta: number) => {
    const next = Math.max(1, Math.min(120, alertThresholdDays + delta));
    update({ alertThresholdDays: next });
    setThresholdInput(String(next));
  };

  const anchorDate = a.end_date || TODAY;
  const targetDate = addDays(anchorDate, alertThresholdDays);
  const targetFormattedDate = targetDate ? formatDate(targetDate) : '';

  const numInputVal = parseInt(thresholdInput, 10);
  const isUnderMin = !Number.isNaN(numInputVal) && numInputVal < 1;
  const isOverMax = !Number.isNaN(numInputVal) && numInputVal > 120;
  const isInputEmpty = thresholdInput.trim() === '';

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

        <div className="flex items-center gap-2 self-start sm:self-auto font-mono text-[11px] text-muted-foreground">
          <span>Continuous In-Process Daemon</span>
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
              <span className={cn('figures text-3xl font-bold tracking-tight', runwayDays <= 0 ? 'text-destructive' : 'text-foreground')}>
                {runwayDays <= 0 ? 0 : runwayDays}
              </span>
              <span className="text-xs text-muted-foreground">
                {runwayDays <= 0 ? 'days remaining (depleted)' : 'days until deficit'}
              </span>
            </div>
            <p className={cn('mt-2 text-xs truncate', runwayDays <= 0 ? 'text-destructive font-medium' : 'text-ink-2')}>
              {runwayDays <= 0 ? 'Cash buffer depleted today · Overdraft imminent' : `Shortfall on ${deficitFormattedDate}`}
            </p>
          </div>

          {/* Card B: Warning Threshold with Editable Input, Presets, and Target Date */}
          <div className="rounded-xl border bg-background/50 p-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Warning Threshold</span>
              <span className="font-mono text-[10px] uppercase tracking-wider text-primary">Policy Rule</span>
            </div>
            <div className="mt-2 flex items-center justify-between">
              <div className="flex items-center gap-1.5 min-w-0">
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  value={thresholdInput}
                  onChange={(e) => {
                    const raw = e.target.value.replace(/[^0-9]/g, '');
                    setThresholdInput(raw);
                    const val = parseInt(raw, 10);
                    if (!Number.isNaN(val) && val >= 1 && val <= 120) {
                      update({ alertThresholdDays: val });
                    }
                  }}
                  onBlur={() => {
                    const val = parseInt(thresholdInput, 10);
                    if (Number.isNaN(val) || val < 1) {
                      update({ alertThresholdDays: 1 });
                      setThresholdInput('1');
                    } else if (val > 120) {
                      update({ alertThresholdDays: 120 });
                      setThresholdInput('120');
                    }
                  }}
                  className={cn(
                    'figures w-14 h-9 rounded-md border bg-background px-1 text-center text-2xl font-bold tracking-tight text-foreground focus:outline-hidden focus:ring-1 tabular-nums transition-colors [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none',
                    isUnderMin || isOverMax || isInputEmpty
                      ? 'border-warning/70 focus:border-warning focus:ring-warning'
                      : 'border-input/60 focus:border-primary focus:ring-primary'
                  )}
                  aria-label="Warning threshold days"
                />
                <span className="text-xs text-muted-foreground leading-tight">
                  days safety target
                </span>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  onClick={() => handleAdjustThreshold(-5)}
                  disabled={alertThresholdDays <= 1}
                  className="flex size-7 items-center justify-center rounded-md border bg-card hover:bg-muted text-foreground transition-colors active:scale-95 disabled:opacity-35 disabled:cursor-not-allowed"
                  title={alertThresholdDays <= 1 ? 'Minimum 1 day threshold reached' : 'Decrease threshold by 5 days'}
                  aria-label="Decrease threshold"
                >
                  <Minus className="size-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => handleAdjustThreshold(5)}
                  disabled={alertThresholdDays >= 120}
                  className="flex size-7 items-center justify-center rounded-md border bg-card hover:bg-muted text-foreground transition-colors active:scale-95 disabled:opacity-35 disabled:cursor-not-allowed"
                  title={alertThresholdDays >= 120 ? 'Maximum 120 days horizon reached' : 'Increase threshold by 5 days'}
                  aria-label="Increase threshold"
                >
                  <Plus className="size-3.5" />
                </button>
              </div>
            </div>

            {/* Target Date or Exception Feedback */}
            {isUnderMin ? (
              <p className="mt-2 text-xs text-warning-text font-medium truncate">
                ⚠️ Minimum threshold is 1 day
              </p>
            ) : isOverMax ? (
              <p className="mt-2 text-xs text-warning-text font-medium truncate">
                ⚠️ Max horizon is 120 days (treasury policy)
              </p>
            ) : isInputEmpty ? (
              <p className="mt-2 text-xs text-muted-foreground truncate">
                Enter between 1 and 120 days
              </p>
            ) : (
              <p className="mt-2 text-xs text-ink-2 truncate">
                Buffer through <span className="font-medium text-foreground">{targetFormattedDate}</span>
              </p>
            )}

            {/* Quick Preset Pills */}
            <div className="mt-2.5 flex items-center gap-1.5 pt-2 border-t border-border/40">
              <span className="text-[10px] uppercase font-mono text-muted-foreground mr-0.5">Presets:</span>
              {[14, 30, 45, 60].map((days) => (
                <button
                  key={days}
                  type="button"
                  onClick={() => {
                    update({ alertThresholdDays: days });
                    setThresholdInput(String(days));
                  }}
                  className={cn(
                    'rounded-md px-2 py-0.5 text-[11px] font-mono transition-colors',
                    alertThresholdDays === days
                      ? 'bg-primary/15 text-primary font-semibold border border-primary/30'
                      : 'bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground border border-transparent'
                  )}
                >
                  {days}d
                </button>
              ))}
            </div>
          </div>

          {/* Card C: Sentinel Decision State */}
          <div className={cn(
            'rounded-xl border p-4 sm:col-span-2 lg:col-span-1 transition-colors',
            runwayDays <= 0 ? 'border-destructive/40 bg-destructive/10' : isTriggered ? 'border-warning/40 bg-warning/10' : 'border-good/30 bg-good/5'
          )}>
            <div className="flex items-center justify-between text-xs">
              <span className={cn('font-semibold uppercase tracking-wider text-[10px]',
                runwayDays <= 0 ? 'text-destructive font-bold' : isTriggered ? 'text-warning-text' : 'text-good-text'
              )}>
                {runwayDays <= 0 ? 'Critical Deficit · Out of Cash' : isTriggered ? 'Trigger Condition Met' : 'Solvent & Protected'}
              </span>
              {runwayDays <= 0 ? (
                <AlertTriangle className="size-4 text-destructive shrink-0" aria-hidden />
              ) : isTriggered ? (
                <AlertTriangle className="size-4 text-warning-text shrink-0" aria-hidden />
              ) : (
                <CheckCircle2 className="size-4 text-good-text shrink-0" aria-hidden />
              )}
            </div>
            <p className="mt-2 text-base font-semibold text-foreground">
              {runwayDays <= 0
                ? '0 days left · Intervention required'
                : isTriggered
                  ? t('sentinel.deltaTriggered', { n: deltaDays })
                  : t('sentinel.deltaSafe', { n: deltaDays })}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {runwayDays <= 0
                ? 'Cash buffer fully depleted. Autonomous bridge line proposal staged in Tier 2.'
                : isTriggered
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
                runwayDays <= 0 ? 'bg-destructive' : isTriggered ? 'bg-warning' : 'bg-good'
              )}
            />
          </div>
          <div className="flex items-center justify-between text-[10.5px] text-muted-foreground">
            <span>0 days</span>
            <span className="font-medium text-foreground">Target: {alertThresholdDays}d</span>
            <span>{Math.round(maxDisplayDays)} days</span>
          </div>
        </div>

        {/* 3. Continuous Verification Pipeline */}
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
                <span className="mt-1 inline-block font-mono text-[10px] text-ink-2">
                  Ledger Reconciled · Decimal Accuracy
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
                <span className="mt-1 inline-block font-mono text-[10px] text-ink-2">
                  Cash Flow Simulation Model
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
                <span className="mt-1 inline-block font-mono text-[10px] text-ink-2">
                  Truth-in-Lending Act (36% APR Cap)
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
                <span className="mt-1 inline-block font-mono text-[10px] text-ink-2">
                  Queue-Only · Execution Strictly Refused
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
              <span className="font-medium text-foreground">Three-Tier Governance:</span> Proposals are staged in Tier 2 queue only. No funds move without owner confirmation.
            </span>
          </div>

          {pending && (
            <Button asChild size="sm" variant="outline" className="shrink-0 text-xs gap-1.5 shadow-xs">
              <Link href="/assistant">
                <span>Review Staged Proposal in Assistant</span>
                <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            </Button>
          )}
        </div>
      </div>
    </motion.section>
  );
}
