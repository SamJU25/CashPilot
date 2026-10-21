export interface DailyPoint {
  date: string;
  cents: number;
}

export interface WeekChange {
  /** Monday of the week. */
  week: string;
  cents: number;
}

function monday(iso: string) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
}

/**
 * Net change in balance per calendar week, from the daily balance series alone: the closing balance of
 * each week minus the closing balance of the week before. The first week is measured from its first day.
 */
export function weeklyNet(points: DailyPoint[]): WeekChange[] {
  const closing = new Map<string, number>();
  let first: number | null = null;
  for (const p of points) {
    first ??= p.cents;
    closing.set(monday(p.date), p.cents);
  }
  const out: WeekChange[] = [];
  let prev = first ?? 0;
  for (const [week, cents] of closing) {
    out.push({ week, cents: cents - prev });
    prev = cents;
  }
  return out;
}
