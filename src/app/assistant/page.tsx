'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import Link from 'next/link';
import { ArrowUp, ArrowUpRight, Check, Clock, Copy, Download, FileText, MessageSquare, PanelRightOpen, Pencil, Square, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ErrorState, LoadingBlock } from '@/components/common/states';
import { RunReceipt } from '@/components/copilot/run-receipt';
import { centsToString, formatDate, formatMoney } from '@/lib/format';
import { useT, type Key, type T } from '@/lib/i18n';
import { ANALYSIS, ANCHOR, BASE, COMPARE_DAYS, DOSSIER, INTENTS, OPTIONS, RECEIVABLES, SAMPLE_CSV, costToBorrow } from '@/lib/mock/demo';
import { fade, spring } from '@/lib/motion';
import { PROVIDERS, providerName } from '@/lib/providers';
import { ModelMenu } from '@/components/copilot/model-menu';
import { modelLabel, useActiveLocalModel } from '@/lib/local-models';
import { ThinkingIndicator } from '@/components/copilot/thinking-block';
import { AnswerMarkdown } from '@/components/copilot/answer-markdown';
import { useData } from '@/lib/use-data';
import { useIntents, useWorkspace } from '@/lib/workspace';
import { ApiError, api, llmConfig, type ProposedEntry } from '@/lib/api';
import { Briefing } from '@/components/copilot/briefing';
import { EntryCard, type EntryStatus } from '@/components/copilot/entry-card';
import type { ActionType, IntentStatus, RunStep, StagedActionIntent } from '@/lib/types';
import { AssistantInspector } from '@/components/copilot/assistant-inspector';
import { cn } from '@/lib/utils';

interface Message {
  id: number;
  // 'switch' marks where the conversation moved to another model.
  role: 'user' | 'copilot' | 'switch';
  text: string;
  steps?: RunStep[];
  model?: string;
  /** A drafted action shown as an approval card under the answer; only its Prepare request button changes its status. */
  actionId?: string;
  /** A cash entry read from the owner's message; only the card's Record button records it. */
  entry?: ProposedEntry;
  entryStatus?: EntryStatus;
  timestamp?: string;
}

const CHAT_KEY = 'cashpilot.chat.v2';
// Older turns live on in the backend's rolling summary, so the visible chat can drop them.
const MAX_CHAT_MESSAGES = 100;
// The model sees this many recent messages word for word (backend: history[-6:]).
const VERBATIM_MESSAGES = 6;

/** Appends and keeps the newest MAX_CHAT_MESSAGES; ids continue from the last one so keys stay unique after trimming. */
function appendCapped(list: Message[], ...items: Omit<Message, 'id'>[]): Message[] {
  let next = (list[list.length - 1]?.id ?? -1) + 1;
  const now = new Date().toISOString();
  return [...list, ...items.map((item) => ({ timestamp: item.timestamp ?? now, ...item, id: next++ }))].slice(-MAX_CHAT_MESSAGES);
}
// shortcut: a fixed pause stands in for model latency; the backend's streamed reply ends it.
const THINK_MS = 1200;

const NO_DATA_SUGGESTIONS: Key[] = ['as.n2', 'as.n3', 'as.s4', 'as.n1'];
const BRIEFED_SUGGESTIONS: Key[] = ['as.s1', 'as.s2', 'as.s3', 'as.s4'];

// KaTeX text labels: drop characters that would break out of \text{…}.
const texLabel = (s: string) => s.replace(/[{}\\$%&#^_~]/g, '');
// "29922.08" -> "29{,}922.08" so KaTeX keeps the thousands comma tight.
const texNumber = (s: string) => s.replace(/\B(?=(\d{3})+(?!\d))/g, '{,}');

// Knowledge cards are `## sections` of knowledge/cards/*.md (services/agent/knowledge.py).
const CARDS = {
  runway: { file: 'cash_liquidity.md', title: 'Cash Runway', slug: 'runway' },
  dscr: { file: 'credit_debt.md', title: 'Debt Service Coverage Ratio (DSCR)', slug: 'dscr' },
  factor: { file: 'financing.md', title: 'Factor Rate vs APR', slug: 'factor' },
  fx: { file: 'cash_liquidity.md', title: 'Foreign Exchange (FX) Rate Volatility & Hedging', slug: 'fx' },
  dab: { file: 'cash_liquidity.md', title: 'Daily Average Balance (DAB)', slug: 'dab' },
  dir: { file: 'cash_liquidity.md', title: 'Defensive Interval Ratio (DIR)', slug: 'dir' },
  fccr: { file: 'credit_debt.md', title: 'Fixed Charge Coverage Ratio (FCCR)', slug: 'fccr' },
  altman: { file: 'credit_debt.md', title: "Altman Z'-Score", slug: 'altman' },
  ccc: { file: 'working_capital.md', title: 'Cash Conversion Cycle (CCC)', slug: 'ccc' },
  wcr: { file: 'working_capital.md', title: 'Working Capital Requirement (WCR)', slug: 'wcr' },
  dso: { file: 'working_capital.md', title: 'Days Sales Outstanding (DSO)', slug: 'dso' },
  dupont: { file: 'profitability_unit_economics.md', title: 'DuPont 3-Stage ROE Analysis', slug: 'dupont' },
  dcf: { file: 'profitability_unit_economics.md', title: 'Discounted Cash Flow (DCF)', slug: 'dcf' },
  breakeven: { file: 'profitability_unit_economics.md', title: 'Contribution Margin & Break-Even Analysis', slug: 'breakeven' },
} as const;
type Topic = 'cash' | 'credit' | 'receivables' | 'knowledge' | 'action';
type Answer = Pick<Message, 'text' | 'steps'>;

/** First step of every answer: the supervisor's semantic router picks the intent. */
function routeStep(t: T, topic: Topic, intent: string, similarity: string): RunStep {
  return {
    label: t('as.k0'),
    detail: t('as.k0d', { topic: t(`topic.${topic}` as Key) }),
    agent: 'supervisor',
    tool: 'FastEmbedSemanticRouter',
    tech: `${intent} · cosine ${similarity}`,
    duration_ms: 14,
  };
}

function cardStep(t: T, card: keyof typeof CARDS, similarity: string): RunStep {
  return {
    label: t('as.k1'),
    detail: t('as.k1d', { name: t(`card.${card}` as Key) }),
    agent: 'supervisor',
    card: CARDS[card],
    tech: `similarity ${similarity}`,
    duration_ms: 6,
  };
}

function formulaAnswer(t: T, lang: string, noData: boolean): Answer {
  if (noData) {
    const [lr, lc, lb] = [t('as.f.runway'), t('as.f.cash'), t('as.f.burn')].map(texLabel);
    return {
      text: [t('as.f.title'), `$$\n\\text{${lr}} = \\frac{\\text{${lc}}}{\\text{${lb}}}\n$$`, t('as.f.noteNoData')].join('\n\n'),
      steps: [routeStep(t, 'knowledge', 'GENERAL_ASSISTANCE/RUNWAY', '0.77'), cardStep(t, 'runway', '0.88')],
    };
  }
  const cash = ANALYSIS.current_balance;
  const burn = ANALYSIS.average_daily_burn;
  // Display-only ratio; money itself stays a decimal string.
  const runway = (Number(cash) / Number(burn)).toFixed(1);
  const label = (s: string) => (lang.startsWith('zh') ? `${s}：` : `${s}: `);
  const [lr, lc, lb, ld] = [t('as.f.runway'), t('as.f.cash'), t('as.f.burn'), t('as.f.days')].map(texLabel);
  return {
    text: [
      t('as.f.title'),
      `$$\n\\text{${lr}} = \\frac{\\text{${lc}}}{\\text{${lb}}}\n$$`,
      t('as.f.with'),
      `$$\n\\frac{${texNumber(cash)}}{${texNumber(burn)}} \\approx ${runway}\\ \\text{${ld}}\n$$`,
      `- ${label(t('as.f.cash'))}${formatMoney(cash)}\n- ${label(t('as.f.burn'))}${formatMoney(burn)}`,
      t('as.f.note', { date: formatDate(BASE.forecast.projected_deficit_date!) }),
    ].join('\n\n'),
    steps: [
      routeStep(t, 'cash', 'CASH_DIAGNOSTIC/RUNWAY', '0.79'),
      cardStep(t, 'runway', '0.88'),
      { label: t('as.c1'), detail: t('as.c1d', { from: formatDate('2026-08-01'), to: formatDate(ANCHOR) }), agent: 'liquidity', tool: 'tool_analyze_cash_flow', duration_ms: 31 },
    ],
  };
}

const FORMULA_RE = /(formula|calculat|how is|公式|怎么算|怎麼算|计算|計算|fórmula|calcula|सूत्र|गणना|সূত্র|হিসাব হয়)/;
// Typed approval is recognised only to explain that it cannot work; it never changes an action's status.
const APPROVE_RE = /(^(yes|yeah|ok|okay|sure)\b|approve|confirm|go ahead|do it|批准|同意|确认|確認|核准|aprob|confirm|^sí\b|मंज़ूर|हाँ|अनुमोदन|অনুমোদন|হ্যাঁ)/;
const DRAFT_RE = /(draft|cover the shortfall|cover it|draw|bridge|起草|草擬|提款|动用|動用|补足|補足|redact|prepar|disponer|cubrir|ड्राफ़्ट|निकासी|খসড়া|উত্তোলন)/;
const DRAW_INTENT = INTENTS.find((i) => i.action_type === 'DRAW_CREDIT_LINE')!;
const DSCR_RE = /(dscr|debt service|偿债|償債|cobertura|डेट सर्विस|ডেট সার্ভিস)/;
const FACTOR_RE = /(factor|系数|係數|फ़ैक्टर|ফ্যাক্টর)/;
const CCC_RE = /(ccc|conversion cycle|working capital cycle|周转期|週轉期|ciclo de conversión|कन्वर्ज़न साइकिल|কনভার্সন সাইকেল)/;
const CASH_RE = /(short|run out|runway|cash|forecast|payroll|现金|現金|缺口|不足|预测|預測|工资|工資|余额|餘額|efectivo|caja|falta|pronóstico|nómina|saldo|नकद|कमी|पूर्वानुमान|वेतन|बैलेंस|নগদ|ঘাটতি|পূর্বাভাস|বেতন|ব্যালেন্স)/;
const LENDER_RE = /(lender|loan|borrow|cheap|apr|fund|credit|资金方|資金方|贷款|貸款|借|便宜|利率|融资|融資|授信|prestamista|préstamo|barato|tasa|financ|crédito|ऋण|लोन|सस्ता|ब्याज|फंडिंग|ঋণ|সস্তা|সুদ|অর্থায়ন)/;
const RECV_RE = /(owe|chase|customer|invoice|receivable|late|欠|催|客户|客戶|发票|發票|应收|應收|逾期|deb|cobr|cliente|factura|atras|बकाया|ग्राहक|इनवॉइस|वसूली|পাওনা|গ্রাহক|ইনভয়েস|বকেয়া)/;

/** Markdown table; `right` marks numeric columns, which right-align. */
function mdTable(head: string[], rows: string[][], right: boolean[]) {
  const cell = (s: string) => s.replace(/\|/g, '\\|');
  return [
    `| ${head.map(cell).join(' | ')} |`,
    `|${right.map((r) => (r ? ' ---: ' : ' --- ')).join('|')}|`,
    ...rows.map((r) => `| ${r.map(cell).join(' | ')} |`),
  ].join('\n');
}

function dscrAnswer(t: T): Answer {
  const [noi, debt] = [t('as.dscr.noi'), t('as.dscr.debt')].map(texLabel);
  return {
    text: [
      t('as.dscr.lead'),
      `$$\n\\text{DSCR} = \\frac{\\text{${noi}}}{\\text{${debt}}}\n$$`,
      [t('as.dscr.b1'), t('as.dscr.b2'), t('as.dscr.b3')].map((b) => `- ${b}`).join('\n'),
    ].join('\n\n'),
    steps: [routeStep(t, 'knowledge', 'GENERAL_ASSISTANCE/DSCR', '0.84'), cardStep(t, 'dscr', '0.91')],
  };
}

function factorAnswer(t: T): Answer {
  const principal = 1_000_000; // cents, a round example the owner can scale in their head
  const days = 180;
  const [lf, ld] = [t('as.fr.factor'), t('as.f.days')].map(texLabel);
  const rows = ['1.10', '1.25', '1.35'].map((factor) => {
    // Display-only example; matches the APR conversion in services/matcher (factor-rate to APR).
    const apr = ((Number(factor) - 1) * (365 / days) * 100).toFixed(1);
    return [factor, t('as.fr.months', { n: days / 30 }), formatMoney(centsToString(Math.round(principal * Number(factor)))), `${apr}%`];
  });
  return {
    text: [
      t('as.fr.lead'),
      `$$\n\\text{APR} \\approx (\\text{${lf}} - 1) \\times \\frac{365}{\\text{${ld}}}\n$$`,
      mdTable([t('as.fr.factor'), t('as.fr.term'), t('as.fr.repay', { amount: formatMoney(centsToString(principal), undefined, { cents: false }) }), t('as.fr.apr')], rows, [true, true, true, true]),
      t('as.fr.note'),
    ].join('\n\n'),
    steps: [
      routeStep(t, 'knowledge', 'GENERAL_ASSISTANCE/FACTORING', '0.82'),
      cardStep(t, 'factor', '0.89'),
      { label: t('as.l2'), detail: t('as.l2d'), agent: 'credit', tool: 'convert_factor_rate_to_apr', tech: 'services/matcher', duration_ms: 4 },
    ],
  };
}

function cccAnswer(t: T): Answer {
  const [dso, dio, dpo] = [t('as.ccc.dso'), t('as.ccc.dio'), t('as.ccc.dpo')].map(texLabel);
  return {
    text: [
      t('as.ccc.lead'),
      `$$\n\\text{CCC} = \\text{${dso}} + \\text{${dio}} - \\text{${dpo}}\n$$`,
      [t('as.ccc.b1'), t('as.ccc.b2'), t('as.ccc.b3')].map((b) => `- ${b}`).join('\n'),
    ].join('\n\n'),
    steps: [routeStep(t, 'knowledge', 'GENERAL_ASSISTANCE/WORKING_CAPITAL', '0.86'), cardStep(t, 'ccc', '0.93')],
  };
}

function lenderTable(t: T) {
  const needCents = Number(BASE.forecast.recommended_bridge_amount.replace('.', ''));
  const sorted = [...OPTIONS].sort((a, b) => Number(a.is_predatory) - Number(b.is_predatory) || b.suitability_score - a.suitability_score);
  return mdTable(
    [t('as.t.lender'), t('as.t.apr'), t('as.t.cost', { amount: formatMoney(centsToString(needCents), undefined, { cents: false }), days: COMPARE_DAYS }), t('as.t.fit')],
    sorted.map((o) => [
      o.is_predatory ? `**${o.provider}** ⚠` : o.provider,
      o.is_predatory ? `**${o.apr_percent}%**` : `${o.apr_percent}%`,
      formatMoney(centsToString(costToBorrow(needCents, o.apr_percent))),
      `${o.suitability_score}/100`,
    ]),
    [false, true, true, true],
  );
}

// shortcut: preview answers built from sample data; POST /api/v1/agent/chat replaces this.
function answer(q: string, drawStatus: IntentStatus, t: T, lang: string, noData: boolean): Pick<Message, 'text' | 'steps' | 'actionId'> {
  const f = BASE.forecast;
  const s = q.toLowerCase();
  const drawPending = drawStatus === 'STAGED_PENDING_HITL';
  if (!noData && (APPROVE_RE.test(s) || DRAFT_RE.test(s))) {
    const approving = APPROVE_RE.test(s);
    const route = routeStep(t, 'action', approving ? 'ACTION_STAGING/APPROVE' : 'ACTION_STAGING/DRAW_CREDIT_LINE', approving ? '0.88' : '0.86');
    if (!drawPending) {
      return { text: t('as.a.actionDone', { status: t(`status.${drawStatus}` as Key) }), steps: [route], actionId: DRAW_INTENT.id };
    }
    if (approving) {
      return {
        text: t('as.a.typedApprove'),
        steps: [{ ...route, tech: 'ACTION_STAGING/APPROVE · text approval refused: status changes only from the card' }],
        actionId: DRAW_INTENT.id,
      };
    }
    return {
      text: t('as.a.action', {
        amount: formatMoney(centsToString(DRAW_INTENT.amount_cents)),
        lender: DRAW_INTENT.target_identifier,
        date: formatDate(f.projected_deficit_date!),
      }),
      steps: [
        route,
        { label: t('run.s7'), detail: t('run.s7d', { amount: formatMoney(centsToString(DRAW_INTENT.amount_cents)) }), agent: 'risk', tool: 'tool_stage_financial_action', tech: 'security_gate_policy.json · tier 2 draft', duration_ms: 21 },
      ],
      actionId: DRAW_INTENT.id,
    };
  }
  if (CCC_RE.test(s)) return cccAnswer(t);
  if (FORMULA_RE.test(s)) return formulaAnswer(t, lang, noData);
  if (DSCR_RE.test(s)) return dscrAnswer(t);
  if (FACTOR_RE.test(s)) return factorAnswer(t);
  // Without statements nothing about the business is known; mirror the backend's no-invention rule.
  if (noData) {
    if (CASH_RE.test(s) || LENDER_RE.test(s) || RECV_RE.test(s)) {
      return { text: t('as.a.needData'), steps: [{ ...routeStep(t, 'cash', 'CASH_DIAGNOSTIC', '0.74'), tech: 'CASH_DIAGNOSTIC · cosine 0.74 · no statement loaded' }] };
    }
    return { text: t('as.a.intro'), steps: [routeStep(t, 'knowledge', 'GENERAL_ASSISTANCE', '0.61')] };
  }
  if (CASH_RE.test(s)) {
    return {
      text: t('as.a.cash', {
        date: formatDate(f.projected_deficit_date!),
        payroll: formatMoney(f.detected_recurring_payroll!),
        short: formatMoney(f.projected_shortfall_amount),
        later: formatDate('2026-11-01'),
        draw: formatMoney(f.recommended_bridge_amount),
        status: t(drawPending ? 'as.a.pending' : 'as.a.decided'),
      }),
      actionId: drawPending ? DRAW_INTENT.id : undefined,
      steps: [
        routeStep(t, 'cash', 'CASH_DIAGNOSTIC/DEFICIT', '0.81'),
        { label: t('as.c1'), detail: t('as.c1d', { from: formatDate('2026-08-01'), to: formatDate(ANCHOR) }), agent: 'liquidity', tool: 'tool_analyze_cash_flow', duration_ms: 40 },
        { label: t('run.s5'), detail: t('as.c2d'), agent: 'liquidity', tool: 'tool_calculate_predictive_cash', tech: 'deficit_severity_policy.json', duration_ms: 9 },
        {
          label: t('as.c3'),
          detail: t('as.c3d', { date: formatDate(f.projected_deficit_date!) }),
          formula: t('as.c3f', { short: f.projected_shortfall_amount, draw: f.recommended_bridge_amount }),
          agent: 'liquidity',
          tool: 'tool_calculate_predictive_cash',
          duration_ms: 3,
        },
      ],
    };
  }
  if (LENDER_RE.test(s)) {
    const best = OPTIONS[0];
    const worstIndex = OPTIONS.findIndex((o) => o.is_predatory);
    const worst = OPTIONS[worstIndex];
    return {
      text: `${t('as.a.lender', { best: best.provider, apr: best.apr_percent, worst: worst.provider, quote: t(`quote.${worstIndex}` as Key), wapr: worst.apr_percent })}\n\n${lenderTable(t)}`,
      steps: [
        routeStep(t, 'credit', 'CREDIT_UNDERWRITING/OPTIONS', '0.83'),
        { label: t('as.l1'), detail: t('as.l1d', { amount: formatMoney(DOSSIER.max_qualified_limit) }), agent: 'credit', tool: 'tool_underwrite_credit', tech: 'facility_matching_policy.json', duration_ms: 52 },
        { label: t('as.l2'), detail: t('as.l2d'), formula: t('as.l2f'), agent: 'credit', tool: 'convert_factor_rate_to_apr', duration_ms: 6 },
        { label: t('as.l3'), detail: t('as.l3d', { name: worst.provider }), agent: 'risk', tool: 'is_predatory_apr', tech: 'usury_policy.json', duration_ms: 2 },
      ],
    };
  }
  if (RECV_RE.test(s)) {
    const top = RECEIVABLES.top_debtors[0];
    return {
      text: t('as.a.recv', { name: top.customer_name, amount: formatMoney(top.overdue_amount), days: top.max_days_overdue, share: top.share_of_total_ar }),
      steps: [
        routeStep(t, 'receivables', 'CASH_DIAGNOSTIC/RECEIVABLES_AGEING', '0.78'),
        { label: t('as.r1'), detail: t('as.r1d', { amount: formatMoney(RECEIVABLES.total_overdue) }), agent: 'liquidity', tool: 'tool_analyze_receivables_ageing', duration_ms: 18 },
        { label: t('as.r2'), detail: t('as.r2d', { name: top.customer_name }), agent: 'liquidity', tool: 'tool_analyze_receivables_ageing', tech: 'concentration_policy.json', duration_ms: 2 },
      ],
    };
  }
  return { text: t('as.a.fallback'), steps: [routeStep(t, 'knowledge', 'GENERAL_ASSISTANCE', '0.58')] };
}

/** The backend's intent label decides which topic the router step names. */
function topicOf(intent: string): Topic {
  if (/ACTION|STAG/.test(intent)) return 'action';
  if (/RECEIV|INVOICE/.test(intent)) return 'receivables';
  if (/CREDIT|UNDERWRIT|FUND/.test(intent)) return 'credit';
  if (/CASH|LIQUID|RUNWAY|DEFICIT/.test(intent)) return 'cash';
  return 'knowledge';
}

export default function AssistantPage() {
  const { active: activeLocal } = useActiveLocalModel();
  const { ready, hasData, provider, localModel, providerModels, providerKeys, providerUrls, intentStatus, update, source, live: liveData, setLive: setLiveData, alertThresholdDays, homeCurrency, language, clearData } = useWorkspace();
  const { t, lang } = useT();
  const intents = useIntents();
  const drawStatus = intentStatus[DRAW_INTENT.id] ?? DRAW_INTENT.status;
  const state = useData(
    () => true,
    (l) => (l.analysis ? true : null),
  );
  const [waiting, setWaiting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(0);
  const [pondered, setPondered] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);

  const exportTranscript = () => {
    if (messages.length === 0) return;
    const dateStr = new Date().toISOString().slice(0, 10);
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const model = provider === 'local' && activeLocal ? `Local (${modelLabel(activeLocal)})` : (providerName(provider, t, true) ?? provider);

    const lines: string[] = [
      `# CashPilot — Financial Consultation Report`,
      `**Generated:** ${dateStr} ${timeStr}`,
      `**AI Intelligence Model:** ${model}`,
      `**Ledger Mode:** ${hasData ? (source === 'sample' ? 'Sample Business' : 'Live Connected Statements') : 'Unlinked (General Diagnostic)'}`,
      `\n---\n`,
    ];

    for (const m of messages) {
      if (m.role === 'switch') {
        lines.push(`\n*Model switched to ${providerName(m.model ?? '', t) ?? m.model}*\n`);
      } else if (m.role === 'user') {
        lines.push(`### Owner Prompt\n${m.text}\n`);
      } else if (m.role === 'copilot') {
        lines.push(`### CashPilot Diagnostic & Recommendation\n${m.text}\n`);
        if (m.steps && m.steps.length > 0) {
          lines.push(`*Calculation Provenance:* ${m.steps.map((s) => s.tech).filter(Boolean).join(' · ')}\n`);
        }
        lines.push(`\n---\n`);
      }
    }

    lines.push(`\n*Notice: CashPilot is an Autonomous Financial AI Participant. Staged transactions remain non-custodial and require owner transmission.*`);

    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cashpilot-consultation-${dateStr}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const stopGeneration = () => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setWaiting(false);
    setBusy(false);
    setLive(0);
    setPondered(false);
  };

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && (waiting || busy)) {
        e.preventDefault();
        stopGeneration();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [waiting, busy]);

  // Tab-scoped on purpose: the chat survives page switches but not closing the tab, since it holds financial details.
  // Saving waits for the restore, otherwise the empty initial chat overwrites the saved one.
  const [restored, setRestored] = useState(false);
  useEffect(() => {
    if (!ready || restored) return;
    try {
      // A chat about the sample company never carries over to the owner's own files, or back.
      const saved = JSON.parse(window.sessionStorage.getItem(CHAT_KEY) ?? 'null') as { source: string; messages: Message[] } | null;
      if (saved?.source === source) setMessages(saved.messages.slice(-MAX_CHAT_MESSAGES));
    } catch {
      // Unreadable storage: start with an empty chat.
    }
    setRestored(true);
    // Restores once, after the workspace has read which data source is active.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  useEffect(() => {
    const handleNewChat = () => {
      setQueuedMessage(null);
      setMessages([]);
      setDraft('');
      try {
        window.sessionStorage.removeItem(CHAT_KEY);
      } catch {}
    };
    window.addEventListener('cashpilot:new-chat', handleNewChat);
    return () => window.removeEventListener('cashpilot:new-chat', handleNewChat);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('new')) {
      setQueuedMessage(null);
      setMessages([]);
      setDraft('');
      try {
        window.sessionStorage.removeItem(CHAT_KEY);
      } catch {}
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);
  useEffect(() => {
    if (!restored) return;
    try {
      window.sessionStorage.setItem(CHAT_KEY, JSON.stringify({ source, messages }));
    } catch {
      // Blocked storage: the chat lasts until the page changes.
    }
  }, [messages, restored, source]);
  const [draft, setDraft] = useState('');
  const [queuedMessage, setQueuedMessage] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const scrollH = el.scrollHeight;
    el.style.height = `${Math.min(Math.max(scrollH, 40), 220)}px`;
  }, [draft]);
  const pendingCount = intents.filter((i) => (intentStatus[i.id] ?? i.status) === 'STAGED_PENDING_HITL').length;
  // Permanently docked on desktop (xl+); on mobile/tablet it opens via overlay drawer.
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState(false);
  const [inspectorTab, setInspectorTab] = useState<'activity' | 'approvals'>('activity');
  useEffect(() => {
    if (pendingCount > 0) setInspectorTab('approvals');
  }, [pendingCount]);
  const end = useRef<HTMLDivElement>(null);
  // After the owner records an entry, the copilot reports what it changed, from the updated analysis.
  const [reportRecorded, setReportRecorded] = useState(false);
  useEffect(() => {
    const a = liveData.analysis;
    if (!reportRecorded || !a) return;
    setReportRecorded(false);
    const balance = formatMoney(a.current_balance);
    const parts = [a.runway_days != null ? t('as.recorded', { balance, n: a.runway_days }) : t('as.recordedNoRunway', { balance })];
    if (a.forecast?.has_projected_deficit && a.forecast.projected_deficit_date) parts.push(t('as.recordedShort', { date: formatDate(a.forecast.projected_deficit_date) }));
    setMessages((m) => appendCapped(m, { role: 'copilot', text: parts.join(' ') }));
  }, [reportRecorded, liveData.analysis, t]);
  const last = messages[messages.length - 1];
  const [copiedId, setCopiedId] = useState<number | null>(null);

  const copyText = (text: string, id: number) => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(text).catch(() => {});
      setCopiedId(id);
      setTimeout(() => setCopiedId((curr) => (curr === id ? null : curr)), 2000);
    }
  };

  const formatMessageTime = (iso?: string) => {
    if (!iso) return '';
    try {
      return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, live, waiting]);

  useEffect(() => {
    if (!busy || !last) return;
    // Phases: calculation steps, then the model's reasoning streams in, then the answer shows.
    if (live < (last.steps?.length ?? 0)) {
      const timer = window.setTimeout(() => setLive((n) => n + 1), 380);
      return () => window.clearTimeout(timer);
    }
    if (!pondered) {
      const timer = window.setTimeout(() => setPondered(true), THINK_MS);
      return () => window.clearTimeout(timer);
    }
    setBusy(false);
    setLive(0);
    setPondered(false);
  }, [busy, live, pondered, last]);

  // The owner's own files: the backend answers. Steps carry only what the response really reports.
  const sendLive = async (q: string) => {
    const history = messages
      .filter((m) => m.role !== 'switch')
      .slice(-VERBATIM_MESSAGES)
      .map((m) => ({ role: m.role === 'user' ? ('user' as const) : ('agent' as const), text: m.text }));
    setMessages((m) => appendCapped(m, { role: 'user', text: q }));
    setDraft('');
    setWaiting(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const started = performance.now();
    const sentAt = Date.now();
    try {
      const defaultUrl = PROVIDERS.find((p) => p.id === provider)?.baseUrl ?? '';
      const res = await api.chat(
        {
          message: q,
          history,
          alert_threshold_days: alertThresholdDays,
          currency: homeCurrency,
          language,
          has_statement: hasData,
          csv_content: hasData && source === 'sample' ? SAMPLE_CSV : undefined,
          llm_config: llmConfig(provider, providerKeys, providerUrls, defaultUrl, providerModels?.[provider] || (provider === 'local' ? localModel : undefined)),
        },
        controller.signal,
      );
      const staged = res.staged_action;
      if (staged) {
        const intent = {
          id: staged.intent_id,
          tenant_id: '',
          action_type: staged.action_type as ActionType,
          amount_cents: staged.amount_cents,
          target_identifier: staged.target_identifier,
          status: staged.status as IntentStatus,
          staged_at: new Date().toISOString(),
        };
        // A bridge plan can stage several legs while the reply names only the largest; the ledger has them all.
        const ledger = await api.actions().catch(() => [] as StagedActionIntent[]);
        const thisTurn = ledger.filter((i) => Date.parse(i.staged_at) >= sentAt - 30_000);
        const drafted = thisTurn.some((i) => i.id === intent.id) ? thisTurn : [...thisTurn, intent];
        setLiveData({ intents: [...liveData.intents.filter((i) => !drafted.some((d) => d.id === i.id)), ...drafted] });
        setInspectorTab('approvals');
        setMobileInspectorOpen(true);
      }
      const route: RunStep = {
        label: t('as.k0'),
        detail: t('as.k0d', { topic: t(`topic.${topicOf(res.intent_detected)}` as Key) }),
        agent: 'supervisor',
        tool: 'FastEmbedSemanticRouter',
        tech: `${res.intent_detected} · ${provider === 'local' ? (localModel ? `Local GGUF (${localModel})` : 'Local GGUF') : provider} · ${Math.round(performance.now() - started)}ms`,
        duration_ms: Math.round(performance.now() - started),
      };
      setMessages((m) =>
        appendCapped(m, {
          role: 'copilot',
          model: provider,
          text: res.reply,
          steps: [route],
          actionId: staged?.intent_id,
          ...(res.proposed_entry ? { entry: res.proposed_entry, entryStatus: 'pending' as const } : {}),
        }),
      );
    } catch (e) {
      if ((e as Error)?.name === 'AbortError' || (e as DOMException)?.name === 'AbortError' || controller.signal.aborted) {
        return;
      }
      if (source === 'sample') {
        // Fallback to offline preview calculation if server is temporarily unreachable
        const fallback = answer(q, drawStatus, t, lang, noData);
        setMessages((m) => appendCapped(m, { role: 'copilot', model: provider, ...fallback }));
      } else {
        const message = e instanceof ApiError ? e.message : t('common.timeout');
        setMessages((m) => appendCapped(m, { role: 'copilot', text: t('as.a.error', { message }) }));
      }
    } finally {
      setWaiting(false);
      abortRef.current = null;
    }
  };

  // When AI becomes idle, automatically dispatch any queued follow-up message (Antigravity-style)
  useEffect(() => {
    if (!waiting && !busy && queuedMessage) {
      const next = queuedMessage;
      setQueuedMessage(null);
      void sendLive(next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waiting, busy, queuedMessage]);

  const send = (text: string) => {
    const q = text.trim();
    if (!q) return;
    if (busy || waiting) {
      setQueuedMessage(q);
      setDraft('');
      return;
    }
    return void sendLive(q);
  };

  const newChat = () => {
    stopGeneration();
    setQueuedMessage(null);
    setMessages([]);
    setDraft('');
  };

  const switchModel = (id: string, model?: string) => {
    update(model ? { provider: id, localModel: model } : { provider: id });
    if (messages.length > 0) setMessages((m) => appendCapped(m, { role: 'switch', text: '', model: id }));
  };
  const isLocal = PROVIDERS.find((p) => p.id === provider)?.local ?? true;
  // Index of the first message the model still sees word for word; older ones reach it only as a summary.
  const conversational = messages.flatMap((m, i) => (m.role === 'switch' ? [] : [i]));
  const memoryBoundary = conversational.length > VERBATIM_MESSAGES ? conversational[conversational.length - VERBATIM_MESSAGES] : -1;
  // No statements: the chat still works for definitions and formulas, never for the business's own numbers.
  const noData = state.status === 'empty';
  // With figures loaded, the briefing already covers the shortfall and who to chase; suggest what it does not.
  const suggestions = noData ? NO_DATA_SUGGESTIONS : BRIEFED_SUGGESTIONS;

  const assistantHeader = (
    <header className="flex shrink-0 flex-col gap-3 border-b pb-3 pt-1 sm:flex-row sm:items-center sm:justify-between">
      <div className="space-y-0.5">
        <h1 className="text-xl font-semibold tracking-tight">{t('nav.assistant')}</h1>
        <p className="hidden max-w-xl text-xs leading-normal text-muted-foreground sm:block">
          {provider === 'local' && !activeLocal
            ? t('as.descNoModel')
            : t('as.desc', { model: provider === 'local' && activeLocal ? `Local (${modelLabel(activeLocal)})` : (providerName(provider, t, true) ?? t('rail.notSet')) })}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2 self-start sm:self-center">
        {messages.length > 0 && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={exportTranscript}
            className="h-8 gap-1.5 px-2.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            title={t('as.exportTitle')}
          >
            <Download className="size-3.5" aria-hidden />
            <span className="hidden sm:inline">{t('as.export')}</span>
          </Button>
        )}
        {/* On desktop (xl+) the inspector is permanently docked; mobile/tablet gets a compact drawer trigger */}
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn(
            'xl:hidden relative h-8 gap-1.5 px-2.5 text-xs text-muted-foreground hover:text-foreground transition-colors',
            mobileInspectorOpen && 'bg-muted text-foreground'
          )}
          onClick={() => setMobileInspectorOpen(!mobileInspectorOpen)}
          aria-label={`${t('nav.activity')} & ${t('nav.approvals')}`}
        >
          <PanelRightOpen className="size-3.5" aria-hidden />
          <span>{t('nav.activity')}</span>
          {pendingCount > 0 && (
            <span className="flex size-4 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
              {pendingCount}
            </span>
          )}
        </Button>
      </div>
    </header>
  );

  if (state.status === 'loading') {
    return (
      <div className="flex h-full min-h-0 flex-1 flex-col">
        {assistantHeader}
        <div className="py-6"><LoadingBlock rows={2} /></div>
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className="flex h-full min-h-0 flex-1 flex-col">
        {assistantHeader}
        <div className="py-6"><ErrorState message={state.message} retry={state.retry} /></div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      {assistantHeader}

      <div className="relative flex flex-1 min-h-0 gap-4 xl:gap-6 pt-2">
        <div className="flex flex-1 min-w-0 flex-col max-w-3xl xl:max-w-none">
          <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-1 py-1 space-y-4 flex flex-col">
            <AnimatePresence>
              {messages.length === 0 && !waiting && !busy && (
                <motion.div
                  key="assistant-empty-state"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.98 }}
                  transition={fade}
                  className="my-auto flex flex-col items-center justify-center w-full max-w-2xl mx-auto py-8 space-y-6"
                >
                  {noData && (
                    <div className="w-full max-w-xl mx-auto flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-xl border bg-card/60 p-3.5 text-xs text-muted-foreground shadow-xs">
                      <div className="flex items-center gap-2.5 min-w-0 flex-1">
                        <FileText className="size-4 shrink-0 text-primary" aria-hidden />
                        <span className="leading-relaxed text-foreground/90">{t('as.noData')}</span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <Button asChild size="sm">
                          <Link href="/statements">
                            {t('as.noDataLink')}
                          </Link>
                        </Button>
                      </div>
                    </div>
                  )}

                  {!noData && (
                    <Briefing
                      onAsk={send}
                      onReview={() => {
                        setInspectorTab('approvals');
                        setMobileInspectorOpen(true);
                      }}
                    />
                  )}

                  <div className="w-full max-w-xl mx-auto space-y-2.5">
                    <p className="text-center text-xs font-medium text-muted-foreground">{t('as.try')}</p>
                    <div className="flex flex-col gap-2 w-full">
                      {suggestions.map((key) => (
                        <button
                          key={key}
                          type="button"
                          onClick={() => send(t(key))}
                          className="group flex w-full items-center justify-between rounded-xl border bg-card/80 hover:bg-muted/60 px-4 py-3 text-left text-xs sm:text-[13px] font-medium leading-snug text-foreground shadow-xs transition-all hover:border-border/80 hover:translate-x-0.5 active:scale-[0.99] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        >
                          <span className="min-w-0 flex-1">{t(key)}</span>
                          <ArrowUpRight className="size-4 text-muted-foreground/50 transition-transform group-hover:text-primary group-hover:translate-x-0.5 group-hover:-translate-y-0.5 shrink-0 ml-3" aria-hidden />
                        </button>
                      ))}
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <AnimatePresence initial={false}>
              {messages.map((m, i) => {
                const memoryLine = i === memoryBoundary && (
                  <div className="flex items-center gap-3 text-xs text-muted-foreground" role="note">
                    <span className="h-px flex-1 border-t border-dashed" aria-hidden />
                    {t('as.memory')}
                    <span className="h-px flex-1 border-t border-dashed" aria-hidden />
                  </div>
                );
                const isLast = i === messages.length - 1;
                const isLive = isLast && busy;
                const stepsRunning = isLive && !!m.steps && live < m.steps.length;
                const thinkingLive = isLive && !stepsRunning && !pondered;
                const thinking = stepsRunning || thinkingLive;
                return (
                  <motion.div key={m.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={spring.smooth} className="space-y-4 group">
                    {memoryLine}
                    <div>
                      {m.role === 'switch' ? (
                        <div className="flex items-center gap-3 text-xs text-muted-foreground" role="status">
                          <span className="h-px flex-1 bg-border" aria-hidden />
                          {t('as.switched', { model: providerName(m.model ?? '', t) ?? '' })}
                          <span className="h-px flex-1 bg-border" aria-hidden />
                        </div>
                      ) : m.role === 'user' ? (
                        <div className="flex flex-col items-end">
                          <div className="max-w-[85%] sm:max-w-[75%] whitespace-pre-wrap rounded-2xl rounded-tr-xs bg-muted/80 border border-border/70 px-3.5 py-2 text-[13px] sm:text-[13.5px] leading-relaxed text-foreground shadow-xs">
                            {m.text}
                          </div>
                          <div className="flex items-center gap-2 pt-1 text-[11px] text-muted-foreground opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-150 select-none">
                            {m.timestamp && (
                              <span className="figures text-[11px] text-muted-foreground/80">
                                {formatMessageTime(m.timestamp)}
                              </span>
                            )}
                            <button
                              type="button"
                              onClick={() => {
                                setDraft(m.text);
                                textareaRef.current?.focus();
                              }}
                              className="inline-flex items-center gap-1 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                              title={t('as.edit')}
                              aria-label={t('as.edit')}
                            >
                              <Pencil className="size-3" aria-hidden />
                            </button>
                            <button
                              type="button"
                              onClick={() => copyText(m.text, m.id)}
                              className="inline-flex items-center gap-1 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                              title={copiedId === m.id ? 'Copied' : 'Copy'}
                              aria-label={copiedId === m.id ? 'Copied' : 'Copy'}
                            >
                              {copiedId === m.id ? (
                                <Check className="size-3 text-good-text" aria-hidden />
                              ) : (
                                <Copy className="size-3" aria-hidden />
                              )}
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="space-y-2.5">
                          {m.steps && <RunReceipt steps={m.steps} live={isLive ? live : 0} holdOpen={isLive} />}
                          {thinkingLive && <ThinkingIndicator />}
                          {!thinking && (
                            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                              <AnswerMarkdown text={m.text} />
                              {m.entry && (
                                <div className="mt-3 max-w-md">
                                  <EntryCard
                                    entry={m.entry}
                                    status={m.entryStatus ?? 'pending'}
                                    onStatus={(next) => {
                                      setMessages((list) => list.map((x) => (x.id === m.id ? { ...x, entryStatus: next } : x)));
                                      if (next === 'recorded') setReportRecorded(true);
                                    }}
                                  />
                                </div>
                              )}
                              <div className="flex items-center gap-2 pt-1.5 text-[11px] text-muted-foreground opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-150 select-none">
                                {m.timestamp && (
                                  <span className="figures text-[11px] text-muted-foreground/80">
                                    {formatMessageTime(m.timestamp)}
                                  </span>
                                )}
                                <span className="text-muted-foreground/30" aria-hidden>·</span>
                                <button
                                  type="button"
                                  onClick={() => copyText(m.text, m.id)}
                                  className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                                  title={copiedId === m.id ? t('reminder.copied') : t('as.copyMsg')}
                                  aria-label={copiedId === m.id ? t('reminder.copied') : t('as.copyMsg')}
                                >
                                  {copiedId === m.id ? (
                                    <>
                                      <Check className="size-3 text-good-text" aria-hidden />
                                      <span className="font-medium text-good-text">{t('reminder.copied')}</span>
                                    </>
                                  ) : (
                                    <>
                                      <Copy className="size-3" aria-hidden />
                                      <span>{t('as.copy')}</span>
                                    </>
                                  )}
                                </button>
                              </div>
                            </motion.div>
                          )}
                        </div>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
            {waiting && <ThinkingIndicator />}
            <div ref={end} />
          </div>

          <form
            className="shrink-0 w-full pt-2 pb-1 bg-background"
            onSubmit={(e) => {
              e.preventDefault();
              send(draft);
            }}
          >
            {/* Queued follow-up banner (Antigravity-style) */}
            <AnimatePresence>
              {queuedMessage && (
                <motion.div
                  initial={{ opacity: 0, y: 6, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 4, scale: 0.98 }}
                  transition={spring.snappy}
                  className="mb-2 flex items-center justify-between gap-3 rounded-xl border border-primary/30 bg-primary/5 dark:bg-primary/10 px-3.5 py-2 text-xs backdrop-blur-sm shadow-xs"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/20 text-primary">
                      <Clock className="size-3 animate-pulse" />
                    </span>
                    <div className="min-w-0">
                      <p className="font-medium text-foreground/90 truncate">
                        <span className="text-muted-foreground mr-1.5 font-normal">{t('as.queuedNext')}:</span>
                        "{queuedMessage}"
                      </p>
                      <p className="text-[10.5px] text-muted-foreground">{t('as.queuedNote')}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setDraft(queuedMessage);
                        setQueuedMessage(null);
                        textareaRef.current?.focus();
                      }}
                      className="h-7 px-2 text-xs gap-1 font-medium hover:bg-primary/15 text-foreground"
                      title={t('as.edit')}
                    >
                      <Pencil className="size-3" />
                      <span>{t('as.edit')}</span>
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      onClick={() => setQueuedMessage(null)}
                      className="size-7 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                      title="Cancel queued message"
                    >
                      <X className="size-3.5" />
                    </Button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="relative flex flex-col rounded-2xl border bg-card/75 dark:bg-card/40 backdrop-blur-md shadow-xs focus-within:ring-2 focus-within:ring-primary/25 focus-within:border-primary/50 transition-all p-2.5 gap-1.5">
              <label htmlFor="ask" className="sr-only">
                {t('as.ask')}
              </label>
              <textarea
                ref={textareaRef}
                id="ask"
                rows={1}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    send(draft);
                  }
                }}
                placeholder={t('as.placeholder')}
                className="w-full min-h-[40px] max-h-[220px] resize-none bg-transparent px-2 py-1 text-xs sm:text-[13.5px] leading-relaxed outline-none placeholder:text-muted-foreground/60 overflow-y-auto"
              />

              <div className="flex items-center justify-between pt-1 border-t border-border/40 px-0.5">
                <div className="flex items-center gap-1.5 min-w-0">
                  <ModelMenu onSwitch={switchModel} disabled={busy || waiting} compact />
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="hidden sm:inline-block text-[10.5px] text-muted-foreground/50 select-none">
                    Shift + Enter for new line
                  </span>
                  {waiting || busy ? (
                    <div className="flex items-center gap-1.5">
                      {draft.trim() && (
                        <Button
                          type="submit"
                          size="sm"
                          className="h-7 sm:h-7.5 px-2.5 rounded-lg sm:rounded-xl text-xs gap-1 font-medium transition-all active:scale-95 shadow-xs"
                          title="Queue follow-up to send after current response"
                        >
                          <Clock className="size-3" />
                          <span>{t('as.queue')}</span>
                        </Button>
                      )}
                      <Button
                        type="button"
                        size="icon"
                        variant={draft.trim() ? "outline" : "default"}
                        onClick={stopGeneration}
                        className="size-7 sm:size-7.5 shrink-0 rounded-lg sm:rounded-xl transition-all active:scale-95 shadow-xs"
                        aria-label={t('as.stop')}
                        title={`${t('as.stop')} (Esc)`}
                      >
                        <Square className="size-2.5 sm:size-3 fill-current" />
                      </Button>
                    </div>
                  ) : (
                    <Button
                      type="submit"
                      size="icon"
                      className="size-7 sm:size-7.5 shrink-0 rounded-lg sm:rounded-xl transition-all active:scale-95 disabled:opacity-40"
                      disabled={!draft.trim()}
                      aria-label={t('as.send')}
                    >
                      <ArrowUp className="size-3.5 sm:size-4" />
                    </Button>
                  )}
                </div>
              </div>
            </div>
            <p className="mt-1.5 text-center text-[11px] text-muted-foreground tracking-tight">
              {isLocal ? t('set.localNote') : t('as.mask')}
            </p>
          </form>
        </div>

        {/* Permanently Docked Desktop Inspector Pane */}
        <aside
          className="hidden xl:flex min-h-0 w-[360px] 2xl:w-[400px] shrink-0 flex-col border-l pl-5 2xl:pl-6"
          aria-label={`${t('nav.activity')} & ${t('nav.approvals')}`}
        >
          <AssistantInspector
            activeTab={inspectorTab}
            onTabChange={setInspectorTab}
          />
        </aside>

        {/* Mobile/Tablet Overlay Drawer */}
        <AnimatePresence>
          {mobileInspectorOpen && (
            <div className="xl:hidden fixed inset-0 z-40 flex justify-end">
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setMobileInspectorOpen(false)}
                className="fixed inset-0 bg-background/80 backdrop-blur-xs"
              />
              <motion.aside
                initial={{ x: '100%' }}
                animate={{ x: 0 }}
                exit={{ x: '100%' }}
                transition={spring.smooth}
                className="relative z-50 flex h-full w-[min(380px,calc(100vw-2rem))] flex-col border-l bg-background p-4 shadow-xl"
              >
                <div className="flex items-center justify-between pb-2 mb-2 border-b">
                  <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {t('nav.activity')} & {t('nav.approvals')}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-7 rounded-md text-muted-foreground hover:text-foreground"
                    onClick={() => setMobileInspectorOpen(false)}
                    aria-label="Close"
                  >
                    <X className="size-4" />
                  </Button>
                </div>
                <div className="flex-1 min-h-0">
                  <AssistantInspector
                    activeTab={inspectorTab}
                    onTabChange={setInspectorTab}
                  />
                </div>
              </motion.aside>
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
