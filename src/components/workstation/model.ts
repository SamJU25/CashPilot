import type { TraceEvent, TraceKind } from '@/lib/runs';

export const LANES = ['supervisor', 'liquidity', 'credit', 'risk'] as const;
export type Lane = (typeof LANES)[number];

/** One drawn step: a trace event, or a run of identical consecutive decisions folded into one. */
export interface Step {
  key: string;
  kind: TraceKind;
  name: string;
  /** The lane the step is drawn in; a handoff is drawn in the lane it hands to. */
  lane: Lane;
  start: number;
  duration: number;
  count: number;
  detail: Record<string, string>;
}

const laneOf = (agent: string): Lane => ((LANES as readonly string[]).includes(agent) ? (agent as Lane) : 'supervisor');

/**
 * Turns a trace into the steps the workstation draws. Consecutive decisions with the same domain,
 * agent and outcome are folded (expense sorting runs once per statement category), so the picture
 * shows what was decided rather than how many rows it took.
 */
export function stepsOf(trace: TraceEvent[]): Step[] {
  const steps: Step[] = [];
  for (const e of [...trace].sort((a, b) => a.start_ms - b.start_ms)) {
    const lane = e.kind === 'agent' ? laneOf(e.name) : laneOf(e.agent);
    const prev = steps[steps.length - 1];
    if (prev && e.kind === 'decision' && prev.kind === 'decision' && prev.name === e.name && prev.lane === lane && prev.detail.choice === e.detail.choice) {
      prev.count += 1;
      prev.duration += e.duration_ms;
      continue;
    }
    steps.push({ key: `${steps.length}-${e.kind}-${e.name}`, kind: e.kind, name: e.name, lane, start: e.start_ms, duration: e.duration_ms, count: 1, detail: e.detail });
  }
  return steps;
}

export function summary(trace: TraceEvent[]) {
  const count = (k: TraceKind) => trace.filter((e) => e.kind === k).length;
  const end = Math.max(0, ...trace.map((e) => e.start_ms + e.duration_ms));
  return {
    decisions: count('decision'),
    tools: count('tool'),
    cards: count('card'),
    agents: new Set(trace.filter((e) => e.kind === 'agent').map((e) => e.name)).size,
    ms: end - Math.min(...trace.map((e) => e.start_ms), end),
  };
}

/** Which lanes did anything in this run; the rest are drawn dimmed. */
export function usedLanes(steps: Step[]): Set<Lane> {
  return new Set<Lane>(['supervisor', ...steps.map((s) => s.lane)]);
}

export const ENGINE_LABEL = (engine?: string) =>
  !engine ? '' : engine.startsWith('zen') ? 'wk.engine.rules' : engine.startsWith('system-one') ? 'wk.engine.model' : engine.includes('fallback') ? 'wk.engine.fallback' : '';

// SNAKE_CASE identifiers become words; names already in mixed case (CreditSubagent) are left alone.
export const humanize = (name: string) =>
  /[_]/.test(name) || name === name.toUpperCase()
    ? name
        .replace(/^tool_/, '')
        .toLowerCase()
        .replace(/_/g, ' ')
        .replace(/^\w/, (c) => c.toUpperCase())
    : name;

export const formatMs = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : ms >= 10 ? `${Math.round(ms)} ms` : `${ms.toFixed(1)} ms`);

/* ---- Architecture map: the whole system is always drawn; a run lights up the parts it used. */

// Real inventory, checked against the backend by tests/unit/test_workstation_inventory.py:
// knowledge/cards/*.md, the tools each subagent imports, and the DecisionDomain count.
export const KNOWLEDGE_FILES = [
  'app_safety.md',
  'cash_liquidity.md',
  'credit_debt.md',
  'financing.md',
  'marketing_strategy.md',
  'profitability_unit_economics.md',
  'underwriting_risk.md',
  'working_capital.md',
] as const;

export const DECISION_DOMAINS = 15;

/** Card files to draw: the known ones plus any a newer backend read that this list has not caught up with. */
export const knowledgeFiles = (steps: Step[]) => [
  ...new Set([...KNOWLEDGE_FILES, ...steps.filter((s) => s.kind === 'card' && s.detail.file).map((s) => s.detail.file)]),
];

export const AGENT_TOOLS: Record<Exclude<Lane, 'supervisor'>, { count: number; examples: string[] }> = {
  liquidity: { count: 16, examples: ['tool_analyze_cash_flow', 'tool_run_cash_scenario', 'tool_calculate_ccc'] },
  credit: { count: 17, examples: ['tool_calculate_dscr', 'tool_underwrite_credit', 'tool_calculate_loan_amortization'] },
  risk: { count: 14, examples: ['tool_calculate_break_even', 'tool_calculate_client_concentration', 'tool_calculate_ltv_cac'] },
};

/** Where a step is drawn: one of the supervisor's sub-boxes, or a subagent's panel. */
export type Zone = 'guard' | 'intent' | 'persona' | 'direct' | Exclude<Lane, 'supervisor'>;

export function zoneOf(s: Step): Zone {
  if (s.name === 'SECURITY_GATE') return 'guard';
  if (s.name === 'INTENT_ROUTING') return 'intent';
  if (s.name === 'AGENT_PERSONA') return 'persona';
  return s.lane === 'supervisor' ? 'direct' : s.lane;
}

export type EngineFamily = 'rules' | 'model' | 'fallback';
export const engineFamily = (s: Step): EngineFamily | null =>
  s.detail.fallback === 'true' ? 'fallback' : s.detail.engine?.startsWith('zen') ? 'rules' : s.detail.engine?.startsWith('system-one') ? 'model' : s.detail.engine ? 'fallback' : null;

/** A connector between parts of the map. `at` is the step index that lights it; numbered ones are the signal path. */
export interface Link {
  id: string;
  kind: 'ask' | 'handoff' | 'knowledge' | 'engine' | 'answer';
  to: Zone | 'answer';
  from?: Zone;
  at: number;
  n?: number;
}

/**
 * The connectors a run lit, in the order it lit them: the question into the supervisor, a handoff to
 * each subagent, knowledge read by each part, decisions referred to the engine, and the answer out.
 */
export function linksOf(steps: Step[]): Link[] {
  const links: Link[] = [{ id: 'ask', kind: 'ask', to: 'guard', at: 0 }];
  const seen = new Set<string>();
  let last: Zone = 'direct';
  steps.forEach((s, i) => {
    const z = zoneOf(s);
    const add = (l: Link) => !seen.has(l.id) && (seen.add(l.id), links.push(l));
    if (s.kind === 'agent' && s.lane !== 'supervisor') {
      add({ id: `handoff-${s.lane}`, kind: 'handoff', to: s.lane, at: i });
      last = s.lane;
    }
    if (s.kind === 'card') add({ id: `kn-${z}`, kind: 'knowledge', to: z === 'guard' || z === 'intent' || z === 'persona' ? 'direct' : z, at: i });
    if (s.kind === 'decision') add({ id: `eng-${z === 'guard' || z === 'intent' || z === 'persona' ? 'sup' : z}`, kind: 'engine', to: z, at: i });
  });
  links.push({ id: 'answer', kind: 'answer', from: last, to: 'answer', at: steps.length });
  let n = 0;
  return links.sort((a, b) => a.at - b.at).map((l) => (l.kind === 'engine' ? l : { ...l, n: ++n }));
}
