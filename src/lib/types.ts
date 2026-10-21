// Mirrors backend response models. Money is always a decimal string, never a float.
// Sources: api/routes/analyze.py, api/routes/underwrite.py, services/agent/schema.py,
// services/security/three_tier_gate.py. Fields marked "proposed" are in the backend handoff list.

export type CashStatus = 'CASH_NONPOSITIVE' | 'LOW_RUNWAY' | 'WATCH' | 'NO_BURN';
export type DeficitSeverity = 'SAFE' | 'WATCH' | 'WARNING' | 'CRITICAL';
export type WorkingCapitalStatus = 'WORKING_CAPITAL_TRAP' | 'BALANCED' | 'CASH_GENERATIVE';

export interface RejectedRow {
  row_number: number;
  reason_code: string;
  account_id?: string;
  raw_line?: string;
  suggested_fix?: {
    posted_on?: string;
    amount?: string;
    description?: string;
    transaction_id?: string;
    explanation?: string;
  };
}

export interface AccountSummary {
  file_name: string;
  account_id: string;
  start_date: string;
  end_date: string;
  closing_balance: string;
  transaction_count: number;
}

export interface ContraTransfer {
  outflow_tx_id: string;
  inflow_tx_id: string;
  amount: string;
  outflow_account: string;
  inflow_account: string;
  transfer_date: string;
}

export interface CashAnalysis {
  currency: string;
  accepted_count: number;
  rejected_rows: RejectedRow[];
  current_balance: string;
  net_period_change: string;
  period_days: number;
  average_daily_burn: string;
  runway_days: number | null;
  alert_threshold_days: number;
  cash_status: CashStatus;
  gross_inflows: string | null;
  gross_outflows: string | null;
  cash_conversion_cycle_days: number | null;
  working_capital_status: WorkingCapitalStatus | null;
  start_date: string | null;
  end_date: string | null;
  statement_age_days: number;
  analysis_mode: 'LIVE_OPERATING' | 'HISTORICAL_AUDIT';
  projected_depletion_date: string | null;
  alert_boundary_date?: string | null;
  accounts_breakdown: AccountSummary[] | null;
  internal_transfers_excluded: string | null;
  internal_transfers: ContraTransfer[] | null;
  calendar_gaps: string[] | null;
  has_overlaps_deduped: boolean | null;
  operational_inflows: string | null;
  operational_outflows: string | null;
  document_format: 'CSV' | 'PDF' | 'HYBRID' | 'MANUAL' | null;
  /** Chart data from /analyze: what the statements show, and the forecast from the deficit engine. */
  balance_history?: BalanceAt[] | null;
  account_history?: { account_id: string; points: BalanceAt[] }[] | null;
  recurring_obligations?: RecurringObligation[] | null;
  forecast?: LiveForecast | null;
  projection?: BalanceAt[] | null;
}

export interface BalanceAt {
  date: string;
  balance: string | null;
}

export interface RecurringObligation {
  category: 'PAYROLL' | 'RENT' | 'DEBT_SERVICE';
  amount: string;
  day_of_month: number;
}

export interface LiveForecast extends Forecast {
  /** The day the forecast starts from: the last statement day or the date a balance was entered. */
  anchor_date: string;
}

export interface Forecast {
  has_projected_deficit: boolean;
  severity: DeficitSeverity;
  days_until_deficit: number | null;
  projected_deficit_date: string | null;
  projected_shortfall_amount: string;
  recommended_bridge_amount: string;
  primary_deficit_trigger: string | null;
  detected_recurring_payroll: string | null;
  detected_recurring_rent: string | null;
  detected_recurring_debt: string | null;
}

/** proposed: GET /analyze/series */
export interface BalancePoint {
  date: string;
  balance: string | null;
}
export interface AccountSeries {
  account_id: string;
  display_name: string;
  currency: string;
  points: BalancePoint[];
}

export interface AgeingBucket {
  label: string;
  amount: string;
  percentage: string;
  invoice_count: number;
}

export interface Debtor {
  customer_name: string;
  total_open_balance: string;
  current_amount: string;
  overdue_amount: string;
  max_days_overdue: number;
  invoice_count: number;
  share_of_total_ar: string;
  oldest_unpaid_invoice?: string | null;
}

export interface ReceivablesAgeing {
  currency: string;
  as_of_date: string;
  total_ar: string;
  current_amount: string;
  total_overdue: string;
  overdue_ratio_pct: string;
  weighted_average_days_overdue: string;
  top_1_concentration_pct: string;
  risk_tier: string;
  summary_advisory: string;
  buckets: Record<string, AgeingBucket>;
  top_debtors: Debtor[];
  recommended_actions: string[];
}

export type ProductType = 'WORKING_CAPITAL_LINE' | 'INVOICE_FACTORING' | 'REVENUE_BASED_FINANCING';

export interface UnderwritingDossier {
  currency: string;
  daily_average_balance: string;
  transaction_count: number;
  nsf_count: number;
  risk_tier: 'PRIME' | 'NEAR_PRIME' | 'HIGH_RISK';
  max_qualified_limit: string;
  recommended_product_types: ProductType[];
  revenue_volatility_cv: string | null;
  volatility_tier: string | null;
  liquidity_score: number | null;
  score_tier: string | null;
  conditional_proposal: string | null;
}

export interface FinancingOption {
  provider: string;
  product_type: ProductType;
  facility_name: string;
  max_amount: string;
  term_days: number;
  apr_percent: string;
  is_predatory: boolean;
  suitability_score: number;
  requires_tier_3_hitl: boolean;
  /** proposed: the lender's own pricing wording, shown beside the true APR */
  quoted_as?: string;
}

export type ActionType = 'FACTOR_INVOICE' | 'DRAW_CREDIT_LINE' | 'TRANSFER';
export type IntentStatus = 'STAGED_PENDING_HITL' | 'PREPARED' | 'REJECTED' | 'EXPIRED';

export interface StagedActionIntent {
  id: string;
  tenant_id: string;
  action_type: ActionType;
  amount_cents: number;
  target_identifier: string;
  status: IntentStatus;
  staged_at: string;
  /** proposed: why the agent drafted it */
  rationale?: string;
}

/** proposed: steps on /agent/chat and GET /events */
export type AgentId = 'supervisor' | 'liquidity' | 'credit' | 'risk';

export interface RunStep {
  label: string;
  detail: string;
  formula?: string;
  duration_ms: number;
  /** proposed: which agent ran the step, which tool function it called, which knowledge card it used */
  agent?: AgentId;
  tool?: string;
  card?: { file: string; title: string; slug: string };
  /** proposed: extra technical context, e.g. "intent=CASH_DIAGNOSTIC · similarity 0.71" */
  tech?: string;
}

export interface AgentRun {
  id: string;
  started_at: string;
  trigger: string;
  steps: RunStep[];
  outcome: string;
  tier: 1 | 2 | 3;
}
