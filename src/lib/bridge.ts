import { stringToCents } from '@/lib/format';
import type { RecurringObligation } from '@/lib/types';

export interface Point {
  date: string;
  cents: number;
}

export interface Payment {
  category: RecurringObligation['category'];
  date: string;
  cents: number;
}

const iso = (y: number, m: number, d: number) => new Date(Date.UTC(y, m, d)).toISOString().slice(0, 10);

/** Dates each recurring payment falls on in (from, to]; a day past month end lands on the last day. */
export function paymentsBetween(obligations: RecurringObligation[], from: string, to: string): Payment[] {
  const out: Payment[] = [];
  const month = new Date(`${from.slice(0, 7)}-01T00:00:00Z`);
  while (iso(month.getUTCFullYear(), month.getUTCMonth(), 1) <= to) {
    const y = month.getUTCFullYear();
    const m = month.getUTCMonth();
    const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
    for (const o of obligations) {
      const date = iso(y, m, Math.min(o.day_of_month, last));
      if (date > from && date <= to) out.push({ category: o.category, date, cents: stringToCents(o.amount) });
    }
    month.setUTCMonth(m + 1);
  }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}

export interface Bridge {
  start: Point;
  end: Point;
  payments: Payment[];
  /** Whatever the dated payments do not explain: day-to-day spending net of money coming in. */
  everydayCents: number;
}

/**
 * Splits the forecast's own fall in cash from `start` to `endDate` into the recurring payments that land in
 * between and the remainder. Both balances come from the backend projection, so the steps always add up.
 */
export function cashBridge(points: Point[], obligations: RecurringObligation[], endDate: string): Bridge | null {
  const start = points[0];
  const end = points.find((p) => p.date === endDate);
  if (!start || !end) return null;
  const payments = paymentsBetween(obligations, start.date, end.date);
  const paid = payments.reduce((s, p) => s + p.cents, 0);
  return { start, end, payments, everydayCents: start.cents - end.cents - paid };
}
