import { stringToCents } from '@/lib/format';
import type { CashAnalysis } from '@/lib/types';

/** Monthly operating cash (inflows less non-loan outflows) over the detected monthly loan payment; null when no loan is found. */
export function debtServiceCoverage(a: CashAnalysis): number | null {
  const debt = stringToCents(a.forecast?.detected_recurring_debt ?? '0');
  if (debt <= 0) return null;
  const days = Math.max(a.period_days || 30, 1);
  const monthlyIn = (stringToCents(a.operational_inflows ?? a.gross_inflows ?? '0') / days) * 30;
  const monthlyOut = (stringToCents(a.operational_outflows ?? a.gross_outflows ?? '0') / days) * 30;
  return (monthlyIn - Math.max(0, monthlyOut - debt)) / debt;
}
