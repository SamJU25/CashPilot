// Sample company used until the backend is wired. Values are generated, not hand-typed, so every
// screen agrees: the chart, the hero sentence, the run receipt and the drafted action all come from here.
// shortcut: the forecast mirrors services/calculations/predictive_cash.py in simplified form; replace
// with the proposed GET /analyze/series and a scenario endpoint when the backend ships them.

import { centsToString, formatDate, formatMoney } from '@/lib/format';
import type { T } from '@/lib/i18n';
import type {
  AccountSeries,
  AgentRun,
  CashAnalysis,
  DeficitSeverity,
  FinancingOption,
  Forecast,
  ReceivablesAgeing,
  StagedActionIntent,
  UnderwritingDossier,
} from '@/lib/types';

export const COMPANY = 'Harbor Street Roasters';
export const CURRENCY = 'USD';
export const ANCHOR = '2026-09-30';
export const TODAY = '2026-10-19';
const START = '2026-08-01';
const FORECAST_DAYS = 90;
const ALERT_THRESHOLD_DAYS = 30;

const DAY_MS = 86_400_000;
const toDate = (iso: string) => new Date(`${iso}T00:00:00Z`);
const toIso = (d: Date) => d.toISOString().slice(0, 10);
const addDays = (iso: string, n: number) => toIso(new Date(toDate(iso).getTime() + n * DAY_MS));
const daysBetween = (a: string, b: string) => Math.round((toDate(b).getTime() - toDate(a).getTime()) / DAY_MS);

function rng(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Tx {
  account: string;
  date: string;
  cents: number;
  description: string;
}

interface StatementFile {
  file_name: string;
  account_id: string;
  start: string;
  end: string;
}

export const FILES: StatementFile[] = [
  { file_name: 'chase_operating_august.csv', account_id: 'Account_1', start: '2026-08-01', end: '2026-08-31' },
  { file_name: 'chase_operating_september.csv', account_id: 'Account_1', start: '2026-09-01', end: '2026-09-30' },
  { file_name: 'svb_payroll_august.csv', account_id: 'Account_2', start: '2026-08-01', end: '2026-08-31' },
  { file_name: 'svb_payroll_september.csv', account_id: 'Account_2', start: '2026-09-08', end: '2026-09-30' },
];

export const DEFAULT_ACCOUNT_NAMES: Record<string, string> = {
  Account_1: 'Chase Operating',
  Account_2: 'SVB Payroll',
};

const OPENING: Record<string, number> = { Account_1: 9_990_000, Account_2: 420_000 };
const VENDORS = ['Sysco', 'Coffee bean import', 'PG&E utilities', 'Amazon Business', 'Packaging supply', 'Equipment repair', 'Delivery fuel'];

function generateTransactions(): Tx[] {
  const r = rng(20261019);
  const txs: Tx[] = [];
  for (let i = 0; i <= daysBetween(START, ANCHOR); i++) {
    const date = addDays(START, i);
    const d = toDate(date);
    const dom = d.getUTCDate();
    const weekday = d.getUTCDay() % 6 !== 0;
    if (weekday) txs.push({ account: 'Account_1', date, cents: 170_000 + Math.round(r() * 50_000), description: 'Square settlement' });
    txs.push({
      account: 'Account_1',
      date,
      cents: -(120_000 + Math.round(r() * 100_000)),
      description: VENDORS[Math.floor(r() * VENDORS.length)],
    });
    if (dom === 1) txs.push({ account: 'Account_1', date, cents: -650_000, description: 'Rent, Harbor Properties' });
    if (dom === 15) txs.push({ account: 'Account_1', date, cents: -120_000, description: 'SBA loan payment' });
    if (dom === 26) {
      txs.push({ account: 'Account_1', date, cents: -1_800_000, description: 'Transfer to payroll' });
      txs.push({ account: 'Account_2', date, cents: 1_800_000, description: 'Transfer from operating' });
    }
    if (dom === 28) txs.push({ account: 'Account_2', date, cents: -1_840_000, description: 'Gusto payroll' });
    if (date === '2026-08-12') txs.push({ account: 'Account_2', date, cents: -115_000, description: 'IRS payroll tax deposit' });
  }
  return txs;
}

const TXS = generateTransactions();

function covered(accountId: string, date: string) {
  return FILES.some((f) => f.account_id === accountId && date >= f.start && date <= f.end);
}

/** Daily closing balance per account, in cents. Gap days are null in the series. */
function buildBalances() {
  const running: Record<string, number> = { ...OPENING };
  const rows: { date: string; byAccount: Record<string, number>; total: number }[] = [];
  for (let i = 0; i <= daysBetween(START, ANCHOR); i++) {
    const date = addDays(START, i);
    for (const tx of TXS) if (tx.date === date) running[tx.account] += tx.cents;
    rows.push({ date, byAccount: { ...running }, total: running.Account_1 + running.Account_2 });
  }
  return rows;
}

const BALANCES = buildBalances();
const OPENING_TOTAL = OPENING.Account_1 + OPENING.Account_2;
const CLOSING_TOTAL = BALANCES[BALANCES.length - 1].total;
const PERIOD_DAYS = daysBetween(START, ANCHOR) + 1;
const AVG_DAILY_BURN = Math.round((OPENING_TOTAL - CLOSING_TOTAL) / PERIOD_DAYS);

const RECURRING = [
  { category: 'PAYROLL', cents: 1_840_000, day: 28 },
  { category: 'RENT', cents: 650_000, day: 1 },
  { category: 'DEBT_SERVICE', cents: 120_000, day: 15 },
];
const RECURRING_MONTHLY = RECURRING.reduce((s, o) => s + o.cents, 0);
const VARIABLE_DAILY = Math.max(0, Math.round((AVG_DAILY_BURN * 30 - RECURRING_MONTHLY) / 30));

export const OVERDUE_INVOICE = { customer: 'Northwind Foods', cents: 1_240_000, expected: '2026-10-26', days_overdue: 47 };

export interface Scenario {
  cutPct: number;
  extraMonthlyCents: number;
  collectInvoice: boolean;
}

export const BASE_SCENARIO: Scenario = { cutPct: 0, extraMonthlyCents: 0, collectInvoice: false };

export interface Projection {
  points: { date: string; cents: number }[];
  forecast: Forecast;
}

function severityFor(days: number | null): DeficitSeverity {
  if (days === null) return 'SAFE';
  if (days <= 30) return 'CRITICAL';
  if (days <= 60) return 'WARNING';
  return 'WATCH';
}

export function project(s: Scenario): Projection {
  const variable = Math.round(VARIABLE_DAILY * (1 - s.cutPct / 100));
  let balance = CLOSING_TOTAL;
  const points = [{ date: ANCHOR, cents: balance }];
  let deficitDay: number | null = null;
  let deficitDate: string | null = null;
  let shortfall = 0;
  let trigger: string | null = null;

  for (let i = 1; i <= FORECAST_DAYS; i++) {
    const date = addDays(ANCHOR, i);
    const dom = toDate(date).getUTCDate();
    balance -= variable;
    let dayTrigger = 'OPERATING_BURN';
    for (const ob of RECURRING) {
      if (dom === ob.day) {
        balance -= ob.cents + (ob.category === 'PAYROLL' ? s.extraMonthlyCents : 0);
        dayTrigger = ob.category;
      }
    }
    if (s.collectInvoice && date === OVERDUE_INVOICE.expected) balance += OVERDUE_INVOICE.cents;
    points.push({ date, cents: balance });
    if (balance < 0 && deficitDay === null) {
      deficitDay = i;
      deficitDate = date;
      shortfall = -balance;
      trigger = dayTrigger;
    }
  }

  const bridge = shortfall > 0 ? Math.ceil((shortfall * 1.2) / 50_000) * 50_000 : 0;
  return {
    points,
    forecast: {
      has_projected_deficit: deficitDay !== null,
      severity: severityFor(deficitDay),
      days_until_deficit: deficitDay,
      projected_deficit_date: deficitDate,
      projected_shortfall_amount: centsToString(shortfall),
      recommended_bridge_amount: centsToString(bridge),
      primary_deficit_trigger: trigger,
      detected_recurring_payroll: centsToString(1_840_000),
      detected_recurring_rent: centsToString(650_000),
      detected_recurring_debt: centsToString(120_000),
    },
  };
}

export const BASE = project(BASE_SCENARIO);

export const SERIES: AccountSeries[] = ['Account_1', 'Account_2'].map((id) => ({
  account_id: id,
  display_name: DEFAULT_ACCOUNT_NAMES[id],
  currency: CURRENCY,
  points: BALANCES.map((b) => ({ date: b.date, balance: covered(id, b.date) ? centsToString(b.byAccount[id]) : null })),
}));

export const TOTAL_SERIES = BALANCES.map((b) => ({ date: b.date, cents: b.total }));

const sum = (pred: (t: Tx) => boolean) => TXS.filter(pred).reduce((s, t) => s + t.cents, 0);
const TRANSFERS = TXS.filter((t) => t.description === 'Transfer to payroll');
const TRANSFER_VOLUME = -TRANSFERS.reduce((s, t) => s + t.cents, 0);
const GROSS_IN = sum((t) => t.cents > 0);
const GROSS_OUT = -sum((t) => t.cents < 0);

const runwayDays = Math.floor(CLOSING_TOTAL / AVG_DAILY_BURN);

export const ANALYSIS: CashAnalysis = {
  currency: CURRENCY,
  accepted_count: TXS.length,
  rejected_rows: [
    { row_number: 37, reason_code: 'INVALID_DATE' },
    { row_number: 112, reason_code: 'INVALID_DATE' },
    { row_number: 208, reason_code: 'DUPLICATE_TRANSACTION_ID' },
  ],
  current_balance: centsToString(CLOSING_TOTAL),
  net_period_change: centsToString(CLOSING_TOTAL - OPENING_TOTAL),
  period_days: PERIOD_DAYS,
  average_daily_burn: centsToString(AVG_DAILY_BURN),
  runway_days: runwayDays,
  alert_threshold_days: ALERT_THRESHOLD_DAYS,
  cash_status: runwayDays <= ALERT_THRESHOLD_DAYS ? 'LOW_RUNWAY' : 'WATCH',
  gross_inflows: centsToString(GROSS_IN),
  gross_outflows: centsToString(GROSS_OUT),
  cash_conversion_cycle_days: 41,
  working_capital_status: 'WORKING_CAPITAL_TRAP',
  start_date: START,
  end_date: ANCHOR,
  statement_age_days: daysBetween(ANCHOR, TODAY),
  analysis_mode: 'LIVE_OPERATING',
  projected_depletion_date: addDays(ANCHOR, runwayDays),
  accounts_breakdown: FILES.map((f) => ({
    file_name: f.file_name,
    account_id: f.account_id,
    start_date: f.start,
    end_date: f.end,
    closing_balance: centsToString(
      BALANCES.find((b) => b.date === f.end)!.byAccount[f.account_id],
    ),
    transaction_count: TXS.filter((t) => t.account === f.account_id && t.date >= f.start && t.date <= f.end).length,
  })),
  internal_transfers_excluded: centsToString(TRANSFER_VOLUME),
  internal_transfers: TRANSFERS.map((t, i) => ({
    outflow_tx_id: `OP-${t.date}`,
    inflow_tx_id: `PR-${t.date}`,
    amount: centsToString(-t.cents),
    outflow_account: 'Account_1',
    inflow_account: 'Account_2',
    transfer_date: t.date,
  })),
  calendar_gaps: ['Calendar gap of 7 unrecorded days between 2026-08-31 and 2026-09-08 in Account_2.'],
  has_overlaps_deduped: true,
  operational_inflows: centsToString(GROSS_IN - TRANSFER_VOLUME),
  operational_outflows: centsToString(GROSS_OUT - TRANSFER_VOLUME),
  document_format: 'CSV',
};

export const SPENDING = (() => {
  const groups: Record<string, number> = {};
  // Ids map to cat.* translation keys.
  const label = (d: string) =>
    d.includes('IRS') ? 'tax' :
    d.includes('payroll') ? 'payroll' :
    d.startsWith('Rent') ? 'rent' :
    d.includes('loan') ? 'debt' :
    d.includes('utilities') ? 'utilities' : 'everyday';
  for (const t of TXS) {
    if (t.cents >= 0 || t.description.startsWith('Transfer')) continue;
    groups[label(t.description)] = (groups[label(t.description)] ?? 0) - t.cents;
  }
  return Object.entries(groups)
    .map(([category, cents]) => ({ category, amount: centsToString(cents), cents }))
    .sort((a, b) => b.cents - a.cents);
})();

export const RECEIVABLES: ReceivablesAgeing = {
  currency: CURRENCY,
  as_of_date: ANCHOR,
  total_ar: '38950.00',
  current_amount: '17650.00',
  total_overdue: '21300.00',
  overdue_ratio_pct: '54.69',
  weighted_average_days_overdue: '38.4',
  top_1_concentration_pct: '31.84',
  risk_tier: 'ELEVATED',
  summary_advisory: 'More than half of what customers owe you is overdue, and one customer holds almost a third of it.',
  buckets: {
    current: { label: 'Not yet due', amount: '17650.00', percentage: '45.31', invoice_count: 9 },
    d1_30: { label: '1 to 30 days late', amount: '6150.00', percentage: '15.79', invoice_count: 4 },
    d31_60: { label: '31 to 60 days late', amount: '13950.00', percentage: '35.82', invoice_count: 3 },
    d61_90: { label: '61 to 90 days late', amount: '1200.00', percentage: '3.08', invoice_count: 1 },
    d90_plus: { label: 'Over 90 days late', amount: '0.00', percentage: '0.00', invoice_count: 0 },
  },
  top_debtors: [
    { customer_name: 'Northwind Foods', total_open_balance: '12400.00', current_amount: '0.00', overdue_amount: '12400.00', max_days_overdue: 47, invoice_count: 2, share_of_total_ar: '31.84', oldest_unpaid_invoice: 'INV-2041' },
    { customer_name: 'Pier 9 Cafe Group', total_open_balance: '8650.00', current_amount: '4100.00', overdue_amount: '4550.00', max_days_overdue: 22, invoice_count: 4, share_of_total_ar: '22.21', oldest_unpaid_invoice: 'INV-2058' },
    { customer_name: 'Bayside Grocers', total_open_balance: '7300.00', current_amount: '5150.00', overdue_amount: '2150.00', max_days_overdue: 14, invoice_count: 3, share_of_total_ar: '18.74', oldest_unpaid_invoice: 'INV-2063' },
    { customer_name: 'Lantern Hotel', total_open_balance: '5900.00', current_amount: '5900.00', overdue_amount: '0.00', max_days_overdue: 0, invoice_count: 2, share_of_total_ar: '15.15' },
    { customer_name: 'Mission Bakehouse', total_open_balance: '4700.00', current_amount: '2500.00', overdue_amount: '2200.00', max_days_overdue: 64, invoice_count: 3, share_of_total_ar: '12.07', oldest_unpaid_invoice: 'INV-1997' },
  ],
  recommended_actions: [
    'Ask Northwind Foods for the $12,400.00 overdue since August; collecting it moves your shortfall from Oct 28 to Nov 1.',
    'Offer Mission Bakehouse a payment plan for the invoice 64 days late.',
    'Consider factoring the Northwind invoices if they cannot pay this month.',
  ],
};

export const DOSSIER: UnderwritingDossier = {
  currency: CURRENCY,
  daily_average_balance: '48210.37',
  transaction_count: TXS.length,
  nsf_count: 0,
  risk_tier: 'NEAR_PRIME',
  max_qualified_limit: '40000.00',
  recommended_product_types: ['WORKING_CAPITAL_LINE', 'INVOICE_FACTORING'],
  revenue_volatility_cv: '0.14',
  volatility_tier: 'STABLE',
  liquidity_score: 61,
  score_tier: 'CONDITIONAL',
  conditional_proposal: 'Qualifies for a working capital line up to $40,000.00 if the overdue Northwind invoices are pledged as collateral.',
};

export const OPTIONS: FinancingOption[] = [
  { provider: 'Harbor Community Bank', product_type: 'WORKING_CAPITAL_LINE', facility_name: 'Business line of credit', max_amount: '40000.00', term_days: 365, apr_percent: '11.90', is_predatory: false, suitability_score: 88, requires_tier_3_hitl: true, quoted_as: '11.9% APR, interest only on what you draw' },
  { provider: 'Ledgerline Capital', product_type: 'INVOICE_FACTORING', facility_name: 'Invoice factoring', max_amount: '31160.00', term_days: 60, apr_percent: '18.40', is_predatory: false, suitability_score: 81, requires_tier_3_hitl: true, quoted_as: '3% fee per 60 days on invoices sold' },
  { provider: 'Northgate Revenue Partners', product_type: 'REVENUE_BASED_FINANCING', facility_name: 'Revenue-based financing', max_amount: '25000.00', term_days: 180, apr_percent: '27.50', is_predatory: false, suitability_score: 64, requires_tier_3_hitl: true, quoted_as: '1.12 repayment multiple over 6 months' },
  { provider: 'QuickCash Advance', product_type: 'REVENUE_BASED_FINANCING', facility_name: 'Merchant cash advance', max_amount: '30000.00', term_days: 180, apr_percent: '71.20', is_predatory: true, suitability_score: 12, requires_tier_3_hitl: true, quoted_as: 'Factor rate 1.35 over 6 months' },
];

export const INTENTS: StagedActionIntent[] = [
  {
    id: 'int_7f3a92',
    tenant_id: 'SME-DEFAULT',
    action_type: 'DRAW_CREDIT_LINE',
    amount_cents: Number(BASE.forecast.recommended_bridge_amount.replace('.', '')),
    target_identifier: 'Harbor Community Bank',
    status: 'STAGED_PENDING_HITL',
    staged_at: '2026-10-19T09:12:41Z',
    rationale: `Covers the projected shortfall before payroll on ${formatDate(BASE.forecast.projected_deficit_date ?? ANCHOR)}, with a 20% safety margin. Cheapest suitable offer at 11.9% APR.`,
  },
  {
    id: 'int_51c0de',
    tenant_id: 'SME-DEFAULT',
    action_type: 'FACTOR_INVOICE',
    amount_cents: 980_000,
    target_identifier: 'Ledgerline Capital, INV-2041',
    status: 'REJECTED',
    staged_at: '2026-10-02T15:40:09Z',
    rationale: 'Advance on the Northwind Foods invoice. You chose to collect it directly instead.',
  },
];

export function buildRuns(names: Record<string, string>, t: T): AgentRun[] {
  const f = BASE.forecast;
  const a = names.Account_1 ?? DEFAULT_ACCOUNT_NAMES.Account_1;
  const b = names.Account_2 ?? DEFAULT_ACCOUNT_NAMES.Account_2;
  return [
    {
      id: 'run_0419',
      started_at: '2026-10-19T09:12:30Z',
      trigger: t('run.upload', { n: FILES.length }),
      tier: 2,
      outcome: t('run.uploadOutcome'),
      steps: [
        { label: t('run.s1', { n: FILES.length }), detail: t('run.s1d', { n: ANALYSIS.accepted_count }), agent: 'supervisor', tool: 'parse_bank_csv', tech: 'services/ingestion/csv_parser.py', duration_ms: 420 },
        { label: t('run.s2'), detail: t('run.s2d', { a, b }), agent: 'supervisor', tool: 'consolidate_multi_statement_treasury', tech: 'balance tie-out match', duration_ms: 35 },
        { label: t('run.s3'), detail: t('run.s3d', { amount: formatMoney(ANALYSIS.internal_transfers_excluded!) }), agent: 'liquidity', tool: 'consolidate_multi_statement_treasury', tech: 'contra-transfer elimination', duration_ms: 12 },
        {
          label: t('run.s4'),
          detail: t('run.s4d', { payroll: formatMoney(f.detected_recurring_payroll!), rent: formatMoney(f.detected_recurring_rent!), debt: formatMoney(f.detected_recurring_debt!) }),
          agent: 'liquidity', tool: 'categorize_transaction_description', tech: 'expense_categorization_policy.json', duration_ms: 18,
        },
        {
          label: t('run.s5'),
          detail: f.has_projected_deficit ? t('run.s5d', { date: formatDate(f.projected_deficit_date!), amount: formatMoney(f.projected_shortfall_amount) }) : t('run.s5safe'),
          formula: t('run.s5f', { burn: centsToString(AVG_DAILY_BURN), rec: centsToString(RECURRING_MONTHLY), var: centsToString(VARIABLE_DAILY) }),
          agent: 'liquidity', tool: 'tool_calculate_predictive_cash', tech: 'deficit_severity_policy.json', duration_ms: 9,
        },
        { label: t('run.s6'), detail: t('run.s6d'), agent: 'credit', tool: 'tool_underwrite_credit', tech: 'facility_matching_policy.json · usury_policy.json', duration_ms: 64 },
        {
          label: t('run.s7'),
          detail: t('run.s7d', { amount: formatMoney(f.recommended_bridge_amount) }),
          formula: t('run.s7f', { short: f.projected_shortfall_amount, draw: f.recommended_bridge_amount }),
          agent: 'risk', tool: 'tool_stage_financial_action', tech: 'security_gate_policy.json · tier 2 draft', duration_ms: 21,
        },
      ],
    },
    {
      id: 'run_0402',
      started_at: '2026-10-02T15:39:51Z',
      trigger: t('run2.trigger'),
      tier: 2,
      outcome: t('run2.outcome'),
      steps: [
        { label: t('run2.s1'), detail: t('run2.s1d', { amount: formatMoney(RECEIVABLES.total_ar) }), agent: 'supervisor', tool: 'tool_analyze_receivables_ageing', duration_ms: 140 },
        { label: t('run2.s2'), detail: t('run2.s2d', { amount: formatMoney(RECEIVABLES.total_overdue) }), agent: 'liquidity', tool: 'tool_analyze_receivables_ageing', tech: 'concentration_policy.json', duration_ms: 11 },
        { label: t('run2.s3'), detail: t('run2.s3d'), agent: 'risk', tool: 'tool_verify_invoice_hash', tech: 'SHA-256 invoice fingerprint', duration_ms: 48 },
        { label: t('run2.s4'), detail: t('run2.s4d', { amount: formatMoney('9800.00') }), agent: 'credit', tool: 'tool_calculate_factoring_proceeds', duration_ms: 17 },
      ],
    },
  ];
}

export const COMPARE_DAYS = 60;

// shortcut: simple-interest estimate for side-by-side comparison only; the backend should return
// an exact cost per offer once financing quotes include fee schedules.
export function costToBorrow(amountCents: number, apr: string) {
  const bps = Math.round(Number(apr) * 100);
  return Math.round((amountCents * bps * COMPARE_DAYS) / (10_000 * 365));
}

export type AlertSeverity = 'critical' | 'warning' | 'info';

/** proposed: GET /events. Alerts the agent raised on its own, without being asked. */
export const ALERTS: { id: 'shortfall' | 'overdue' | 'gap'; at: string; severity: AlertSeverity; href: string }[] = [
  { id: 'shortfall', at: '2026-10-19T09:13:05Z', severity: 'critical', href: '/' },
  { id: 'overdue', at: '2026-10-18T08:00:00Z', severity: 'warning', href: '/receivables' },
  { id: 'gap', at: '2026-10-15T07:30:00Z', severity: 'info', href: '/statements' },
];
