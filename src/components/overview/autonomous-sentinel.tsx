'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Minus, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { SplitFlap } from '@/components/common/split-flap';
import { Gauge } from '@/components/charts/kit';
import { centsToString, formatDate, formatMoney } from '@/lib/format';
import { useT } from '@/lib/i18n';
import { addDaysIso, todayIso } from '@/lib/live-forecast';
import { useIntents, useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';
import type { CashAnalysis } from '@/lib/types';
import { api, type SentinelTelemetry } from '@/lib/api';
import { TODAY } from '@/lib/mock/demo';

const MIN_DAYS = 1;
const MAX_DAYS = 120;
const PRESETS = [14, 30, 45, 60];

const clockTime = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

/** Early warning: how far away the shortfall is, the window that triggers a drafted request, and when it last checked. */
export function AutonomousSentinel({ analysis: a }: { analysis: CashAnalysis }) {
  const { t, rich } = useT();
  const { alertThresholdDays, update, source } = useWorkspace();
  const pending = useIntents().find((i) => i.status === 'STAGED_PENDING_HITL');
  const [telemetry, setTelemetry] = useState<SentinelTelemetry | null>(null);
  const [offline, setOffline] = useState(false);
  const [draft, setDraft] = useState(String(alertThresholdDays));

  useEffect(() => setDraft(String(alertThresholdDays)), [alertThresholdDays]);

  // The daemon sweeps on its own interval; this only reads its last result.
  useEffect(() => {
    let mounted = true;
    const read = () =>
      api
        .sentinelHeartbeat()
        .then((d) => mounted && (setTelemetry(d), setOffline(false)))
        .catch(() => mounted && setOffline(true));
    read();
    const id = window.setInterval(read, 15_000);
    return () => {
      mounted = false;
      window.clearInterval(id);
    };
  }, []);

  // A changed window is checked straight away rather than at the next sweep.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      api.sentinelEvaluate().then(() => api.sentinelHeartbeat()).then(setTelemetry).catch(() => {});
    }, 400);
    return () => window.clearTimeout(timer);
  }, [alertThresholdDays]);

  const today = source === 'sample' ? TODAY : todayIso();
  const f = a.forecast ?? null;
  const shortDate = f?.has_projected_deficit ? f.projected_deficit_date : a.projected_depletion_date;
  const days = shortDate ? Math.max(0, Math.round((Date.parse(shortDate) - Date.parse(today)) / 86_400_000)) : null;
  const inside = days !== null && days <= alertThresholdDays;
  const state = days === 0 ? 'out' : inside ? 'inside' : 'clear';

  const setDays = (n: number) => update({ alertThresholdDays: Math.max(MIN_DAYS, Math.min(MAX_DAYS, n)) });
  const scale = Math.max(60, alertThresholdDays * 1.25, (days ?? 0) * 1.25);

  const tone = {
    out: { icon: AlertTriangle, text: 'text-critical-text', gauge: 'text-critical', label: t('sen.out') },
    inside: { icon: AlertTriangle, text: 'text-warning-text', gauge: 'text-warning', label: t('sen.inside') },
    clear: { icon: CheckCircle2, text: 'text-good-text', gauge: 'text-good', label: t('sen.clear') },
  }[state];

  return (
    <div className="space-y-4">
      <section className="grid gap-px overflow-hidden rounded-xl border bg-border lg:grid-cols-[1.4fr_1fr]">
        <div className="grid items-center gap-8 bg-card p-6 sm:p-8 xl:grid-cols-[minmax(0,1fr)_13rem]">
          <div>
            <p className={cn('flex items-center gap-2 text-sm font-medium', tone.text)}>
              <tone.icon className="size-4" aria-hidden />
              {tone.label}
            </p>
            <h2 className="mt-4 font-display text-4xl font-semibold leading-tight tracking-tight">
              {days === null ? t('sen.noShortfall') : rich('sen.runsShortIn', { n: <SplitFlap text={String(days)} /> })}
            </h2>
            {days !== null && shortDate && (
              <p className="mt-4 max-w-[56ch] text-base leading-relaxed text-ink-2">
                {state === 'clear'
                  ? t('sen.clearBody', { date: formatDate(shortDate), n: days - alertThresholdDays, window: alertThresholdDays })
                  : t(pending ? 'sen.insideBodyDraft' : 'sen.insideBody', { date: formatDate(shortDate), window: alertThresholdDays })}
              </p>
            )}
            {inside && pending && (
              <Button asChild className="mt-6">
                <Link href="/assistant">{t('ov.hero.review', { amount: formatMoney(centsToString(pending.amount_cents), undefined, { cents: false }) })}</Link>
              </Button>
            )}
          </div>
          {days !== null && (
            <div>
              <Gauge value={days} max={scale} threshold={alertThresholdDays} tone={tone.gauge} label={t('dash.runwayAria', { n: days, w: alertThresholdDays })}>
                <span className="figures font-display text-3xl font-semibold leading-none">{days}</span>
                <span className="mt-1 text-[11px] text-muted-foreground">{t('dash.daysLeft')}</span>
              </Gauge>
              <p className="mt-3 text-center text-xs text-muted-foreground">{t('dash.windowMark', { n: alertThresholdDays })}</p>
            </div>
          )}
        </div>

        <div className="bg-card p-6 sm:p-8">
          <h3 className="font-display text-xl font-semibold tracking-tight">{t('sen.window')}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{t('sen.windowBody')}</p>

          <div className="mt-6 flex items-center gap-3">
            <Button variant="outline" size="icon" onClick={() => setDays(alertThresholdDays - 1)} disabled={alertThresholdDays <= MIN_DAYS} aria-label={t('sen.fewer')}>
              <Minus aria-hidden />
            </Button>
            <label className="flex items-baseline gap-2">
              <input
                inputMode="numeric"
                value={draft}
                onChange={(e) => {
                  const raw = e.target.value.replace(/[^0-9]/g, '').slice(0, 3);
                  setDraft(raw);
                  const n = Number(raw);
                  if (n >= MIN_DAYS && n <= MAX_DAYS) update({ alertThresholdDays: n });
                }}
                onBlur={() => setDays(Number(draft) || MIN_DAYS)}
                className="figures h-12 w-20 rounded-lg border bg-background text-center font-display text-3xl font-semibold focus-visible:border-primary"
                aria-label={t('sen.window')}
              />
              <span className="text-sm text-muted-foreground">{t('set.days')}</span>
            </label>
            <Button variant="outline" size="icon" onClick={() => setDays(alertThresholdDays + 1)} disabled={alertThresholdDays >= MAX_DAYS} aria-label={t('sen.more')}>
              <Plus aria-hidden />
            </Button>
          </div>

          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={PRESETS.includes(alertThresholdDays) ? String(alertThresholdDays) : ''}
            onValueChange={(v) => v && setDays(Number(v))}
            className="mt-4 justify-start"
            aria-label={t('sen.presets')}
          >
            {PRESETS.map((n) => (
              <ToggleGroupItem key={n} value={String(n)} className="figures px-3">
                {t('chart.days', { n })}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>

          <p className="mt-5 text-sm text-ink-2">{t('sen.windowMeans', { date: formatDate(addDaysIso(today, alertThresholdDays), true) })}</p>
        </div>
      </section>

      <p className="text-sm text-muted-foreground">
        {offline
          ? t('sen.offline')
          : telemetry?.last_sweep_at
            ? t('sen.lastCheck', { time: clockTime(telemetry.last_sweep_at), n: Math.round(telemetry.interval_seconds) })
            : t('sen.starting')}
      </p>
    </div>
  );
}
