// TypeScript interfaces for SME Finance Copilot
// Aligns with docs/system.md Section 3 and Section 4

export type AlertSeverity = 'LOW' | 'MEDIUM' | 'CRITICAL';
export type ActionIntentStatus = 'STAGED_PENDING_HITL' | 'EXECUTED' | 'REJECTED';
export type ActionType = 'FACTOR_INVOICE' | 'DRAW_CREDIT_LINE' | 'TRANSFER';

export interface BankTransaction {
  id: string;
  tenant_id: string;
  post_date: string;
  amount: number;
  counterparty: string;
  category: string;
  is_nsf: boolean;
}

export interface ConformalCorridorPoint {
  date: string;
  p10_pessimistic: number;
  p50_median: number;
  p90_optimistic: number;
}

export interface CashRunwayReport {
  current_cash_balance: number;
  net_daily_burn: number;
  runway_days: number;
  dscr: number;
  dab_30_days: number;
  is_cash_flow_positive: boolean;
  forecast_corridor: ConformalCorridorPoint[];
}

export interface LiveAlertPayload {
  alert_id: string;
  timestamp: string;
  severity: AlertSeverity;
  title: string;
  projected_deficit: number;
  projected_date: string;
  suggested_action_type?: ActionType;
  suggested_amount?: number;
}

export interface ActionIntentDraft {
  id: string;
  tenant_id: string;
  action_type: ActionType;
  amount: number;
  target_identifier: string;
  justification: string;
  status: ActionIntentStatus;
  staged_at: string;
}
