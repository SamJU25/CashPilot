'use client';

import { useMemo, useRef, useState } from 'react';
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { centsToString, formatDate, formatMoney, stringToCents } from '@/lib/format';
import type { Projection } from '@/lib/mock/demo';
import { useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';

type View = 'total' | 'accounts';
type Horizon = 30 | 60 | 90;

const ACCOUNT_COLORS = ['rgb(var(--s1))', 'rgb(var(--s2))', 'rgb(var(--s3))', 'rgb(var(--s4))'];
const INK = 'rgb(var(--foreground))';
const MUTED = 'rgb(var(--muted-foreground))';
const GRID = 'rgb(var(--border))';

// Plotting needs numbers; values are display-only here and never flow back into money state.
const toUnits = (cents: number) => cents / 100;

interface Row {
  date: string;
  total?: number;
  forecast?: number;
  scenario?: number;
  [account: string]: number | string | undefined | null;
}

/** What the statements show: the total per day and each account's own line (null outside its statement). */
export interface ChartHistory {
  total: { date: string; cents: number }[];
  accounts: { account_id: string; points: { date: string; cents: number | null }[] }[];
}

function compact(v: number) {
  // The axis keeps the data's own currency symbol; amounts are shortened to k above a thousand.
  const symbol = formatMoney('0', undefined, { cents: false }).replace('0', '');
  const abs = Math.abs(v);
  const s = abs >= 1000 ? `${Math.round(abs / 1000)}k` : `${Math.round(abs)}`;
  return `${v < 0 ? '−' : ''}${symbol}${s}`;
}

/** A round axis step (1, 2 or 5 times a power of ten) giving about four bands over the range. */
function niceStep(range: number) {
  const raw = Math.max(range, 1) / 4;
  const power = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map((m) => m * power).find((x) => x >= raw) ?? 10 * power;
}

export function RunwayChart({
  history,
  anchor,
  today,
  base,
  scenario,
  gapNote,
}: {
  history: ChartHistory;
  /** Last day the statements (or the typed balance) cover; the forecast starts here. */
  anchor: string;
  today: string;
  base: Projection;
  scenario: Projection | null;
  gapNote?: string;
}) {
  const accounts = history.accounts;
  const { accountNames } = useWorkspace();
  const { t } = useT();
  const [view, setView] = useState<View>('total');
  const [horizon, setHorizon] = useState<Horizon>(60);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const animated = useRef(false);
  const animate = !animated.current;

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = history.total.map((t, i) => {
      const row: Row = { date: t.date, total: toUnits(t.cents) };
      for (const s of accounts) {
        const c = s.points[i]?.cents;
        row[s.account_id] = c === null || c === undefined ? null : toUnits(c);
      }
      return row;
    });
    // The forecast starts at the anchor: on the last statement day it continues that point; after a typed
    // balance with no history (or a later adjustment) it starts a point of its own.
    base.points.slice(0, horizon + 1).forEach((p, i) => {
      const sc = scenario ? toUnits(scenario.points[i].cents) : undefined;
      const last = out[out.length - 1];
      if (last && last.date === p.date) {
        last.forecast = toUnits(p.cents);
        if (scenario) last.scenario = sc;
      } else out.push({ date: p.date, forecast: toUnits(p.cents), scenario: sc });
    });
    return out;
  }, [history, accounts, base, scenario, horizon]);

  const f = base.forecast;
  const deficitInRange = f.projected_deficit_date && f.days_until_deficit! <= horizon;
  const minY = Math.min(0, ...rows.map((r) => Math.min(r.total ?? Infinity, r.forecast ?? Infinity, r.scenario ?? Infinity)));
  const maxY = Math.max(...rows.map((r) => Math.max(r.total ?? -Infinity, r.forecast ?? -Infinity, r.scenario ?? -Infinity)));
  const step = niceStep(maxY - minY);
  const lowest = Math.floor(minY / step) * step;
  const highest = Math.ceil(maxY / step) * step;
  const ticks = Array.from({ length: (highest - lowest) / step + 1 }, (_, i) => lowest + i * step);

  const toggleAccount = (id: string) =>
    setHidden((h) => {
      const next = new Set(h);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4">
        {accounts.length > 1 ? (
          <ToggleGroup type="single" value={view} onValueChange={(v) => v && setView(v as View)} variant="outline" size="sm" aria-label={t('chart.viewLabel')}>
            <ToggleGroupItem value="total">{t('chart.total')}</ToggleGroupItem>
            <ToggleGroupItem value="accounts">{t('chart.byAccount')}</ToggleGroupItem>
          </ToggleGroup>
        ) : (
          <span />
        )}
        <ToggleGroup
          type="single"
          value={String(horizon)}
          onValueChange={(v) => v && setHorizon(Number(v) as Horizon)}
          variant="outline"
          size="sm"
          aria-label={t('chart.horizonLabel')}
        >
          {[30, 60, 90].map((n) => (
            <ToggleGroupItem key={n} value={String(n)}>
              {t('chart.days', { n })}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      <ul className="flex flex-wrap gap-x-5 gap-y-2 pb-3 text-xs text-ink-2" aria-label={t('chart.legend')}>
        {view === 'total' ? (
          <>
            <li className="flex items-center gap-2">
              <span className="h-0.5 w-4 rounded bg-foreground" aria-hidden />
              {t('chart.legend.cash')}
            </li>
            <li className="flex items-center gap-2">
              <span className="w-4 border-t-2 border-dashed border-foreground" aria-hidden />
              {t('chart.legend.forecast')}
            </li>
            {scenario && (
              <li className="flex items-center gap-2">
                <span className="w-4 border-t-2 border-dashed border-primary" aria-hidden />
                {t('chart.legend.changes')}
              </li>
            )}
          </>
        ) : (
          <>
            {accounts.map((s, i) => (
              <li key={s.account_id}>
                <button
                  type="button"
                  onClick={() => toggleAccount(s.account_id)}
                  aria-pressed={!hidden.has(s.account_id)}
                  className={cn('flex items-center gap-2 rounded px-1 py-0.5 transition-opacity hover:bg-muted', hidden.has(s.account_id) && 'opacity-40')}
                >
                  <span className="h-0.5 w-4 rounded" style={{ background: ACCOUNT_COLORS[i % ACCOUNT_COLORS.length] }} aria-hidden />
                  {accountNames[s.account_id] ?? s.account_id}
                </button>
              </li>
            ))}
            <li className="flex items-center gap-2 text-muted-foreground">
              <span className="h-0.5 w-4 rounded bg-muted-foreground/40" aria-hidden />
              {t('chart.total')}
            </li>
          </>
        )}
      </ul>

      <div className="h-[320px] w-full" role="img" aria-label={t('chart.aria', { from: formatDate(rows[0].date), n: horizon })}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 16, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID} strokeDasharray="0" />
            <XAxis
              dataKey="date"
              tickFormatter={(d: string) => formatDate(d)}
              tick={{ fill: MUTED, fontSize: 12 }}
              tickLine={false}
              axisLine={{ stroke: GRID }}
              minTickGap={48}
            />
            <YAxis
              tickFormatter={compact}
              tick={{ fill: MUTED, fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={52}
              domain={[lowest, highest]}
              ticks={ticks}
              className="figures"
            />
            <ReferenceArea y1={lowest} y2={0} fill="rgb(var(--critical))" fillOpacity={0.06} ifOverflow="hidden" />
            <ReferenceLine y={0} stroke="rgb(var(--critical))" strokeOpacity={0.5} />
            {history.total.length > 0 && (
              <ReferenceLine x={anchor} stroke={MUTED} strokeDasharray="2 3" label={{ value: t('chart.stmtEnd'), position: 'insideTopRight', fill: MUTED, fontSize: 11 }} />
            )}
            {today !== anchor && rows.some((r) => r.date === today) && (
              <ReferenceLine x={today} stroke={MUTED} strokeDasharray="2 3" label={{ value: t('chart.today'), position: 'insideTopLeft', fill: MUTED, fontSize: 11 }} />
            )}

            {view === 'accounts' &&
              accounts.map((s, i) => (
                <Line
                  key={s.account_id}
                  dataKey={s.account_id}
                  name={accountNames[s.account_id] ?? s.account_id}
                  stroke={ACCOUNT_COLORS[i % ACCOUNT_COLORS.length]}
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                  hide={hidden.has(s.account_id)}
                  isAnimationActive={false}
                />
              ))}
            <Line
              dataKey="total"
              name={t('chart.total')}
              stroke={view === 'total' ? INK : 'rgb(var(--muted-foreground) / 0.35)'}
              strokeWidth={view === 'total' ? 2 : 1.5}
              dot={false}
              isAnimationActive={animate}
              animationDuration={400}
              animationEasing="ease-out"
              onAnimationEnd={() => (animated.current = true)}
            />
            <Line
              dataKey="forecast"
              name={t('chart.legend.forecast')}
              stroke={view === 'total' ? INK : 'rgb(var(--muted-foreground) / 0.35)'}
              strokeWidth={view === 'total' ? 2 : 1.5}
              strokeDasharray="5 4"
              dot={false}
              isAnimationActive={false}
            />
            {scenario && <Line dataKey="scenario" name={t('chart.legend.changes')} stroke="rgb(var(--primary))" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />}
            {deficitInRange && (
              <ReferenceDot
                x={f.projected_deficit_date!}
                y={toUnits(-stringToCents(f.projected_shortfall_amount))}
                r={5}
                fill="rgb(var(--critical))"
                stroke="rgb(var(--card))"
                strokeWidth={2}
                label={{ value: t('chart.short', { amount: formatMoney(f.projected_shortfall_amount, undefined, { cents: false }) }), position: 'left', offset: 10, fill: 'rgb(var(--critical-text))', fontSize: 12 }}
              />
            )}
            <Tooltip
              cursor={{ stroke: MUTED, strokeWidth: 1 }}
              isAnimationActive={false}
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null;
                const items = payload.filter((p) => p.value !== null && p.value !== undefined && !(view === 'accounts' && hidden.has(String(p.dataKey))));
                return (
                  <div className="min-w-[200px] rounded-md border bg-popover px-3 py-2 text-xs shadow-md">
                    <p className="pb-1.5 font-medium">{formatDate(String(label), true)}</p>
                    <ul className="space-y-1">
                      {items.map((p) => (
                        <li key={String(p.dataKey)} className="flex items-center justify-between gap-4">
                          <span className="flex items-center gap-1.5 text-ink-2">
                            <span className="size-2 rounded-full" style={{ background: String(p.color) }} aria-hidden />
                            {p.name}
                          </span>
                          <span className="figures font-medium">{formatMoney(centsToString(Math.round(Number(p.value) * 100)))}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {view === 'accounts' && gapNote && <p className="pt-3 text-xs text-muted-foreground">{gapNote}</p>}
    </div>
  );
}
