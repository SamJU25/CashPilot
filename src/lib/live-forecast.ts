// Turns the backend's chart data for the owner's own files into the shapes the runway chart and what-if
// panel use. Amounts stay strings until they become integer cents; only the chart converts cents to units.

import { api } from '@/lib/api';
import { centsToString, stringToCents } from '@/lib/format';
import type { ChartHistory } from '@/components/overview/runway-chart';
import type { Projection, Scenario } from '@/lib/mock/demo';
import type { BalanceAt, CashAnalysis, LiveForecast } from '@/lib/types';

const DAY_MS = 86_400_000;

export const addDaysIso = (iso: string, n: number) => new Date(Date.parse(`${iso}T00:00:00Z`) + n * DAY_MS).toISOString().slice(0, 10);

/** Today in the owner's own time zone, as the chart's "Today" line. */
export function todayIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

const toPoints = (points: BalanceAt[]) => points.map((p) => ({ date: p.date, cents: p.balance === null ? 0 : stringToCents(p.balance) }));

export function toProjection(forecast: LiveForecast, projection: BalanceAt[]): Projection {
  return { points: toPoints(projection), forecast };
}

/** The plain forecast /analyze returned, or null when the data predates it or carries none. */
export function liveProjection(a: CashAnalysis): Projection | null {
  return a.forecast && a.projection?.length ? toProjection(a.forecast, a.projection) : null;
}

export function liveHistory(a: CashAnalysis): ChartHistory {
  return {
    total: toPoints(a.balance_history ?? []),
    accounts: (a.account_history ?? []).map((acc) => ({
      account_id: acc.account_id,
      points: acc.points.map((p) => ({ date: p.date, cents: p.balance === null ? null : stringToCents(p.balance) })),
    })),
  };
}

/** Re-runs the forecast on the backend with the what-if levers; the backend is the only place money math runs. */
export async function runScenario(a: CashAnalysis, s: Scenario, collect: { date: string; amount: string } | null): Promise<Projection> {
  const res = await api.scenario({
    current_balance: a.current_balance,
    average_daily_burn: a.average_daily_burn,
    anchor_date: a.forecast!.anchor_date,
    obligations: a.recurring_obligations ?? [],
    variable_cut_pct: String(s.cutPct),
    extra_monthly_payroll: centsToString(s.extraMonthlyCents),
    one_off_inflows: s.collectInvoice && collect ? [collect] : [],
  });
  return toProjection(res.forecast, res.projection);
}
