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

/* ---- Stage layout: steps placed by the kind of work they are, so every run spreads across the sheet. */

export const STAGES = ['ask', 'guard', 'route', 'agent', 'work', 'knowledge', 'answer'] as const;
export type Stage = (typeof STAGES)[number];

export function stageOf(s: Step): Stage {
  if (s.kind === 'agent') return 'agent';
  if (s.kind === 'tool') return 'work';
  if (s.kind === 'card') return 'knowledge';
  if (s.name === 'SECURITY_GATE') return 'guard';
  if (s.name === 'INTENT_ROUTING' || s.name === 'AGENT_PERSONA') return 'route';
  return 'work';
}

/** A drawn node: a step, or one of the synthetic ends (the question, the answer, "the supervisor kept it"). */
export interface Node {
  id: string;
  stage: Stage;
  step: Step | null;
  synthetic?: 'ask' | 'answer' | 'kept';
  x: number;
  y: number;
}

export interface Band {
  stage: Stage;
  y: number;
  h: number;
}

export interface Geometry {
  width: number;
  labelW: number;
  nodeW: number;
  nodeH: number;
  gapX: number;
  gapY: number;
  pad: number;
}

/**
 * Places nodes in stage bands, top to bottom, each band filled left to right in the order the run
 * reached them and wrapped onto further rows when full. The returned order is the signal path:
 * the question, every step in time order, then the answer.
 */
export function layoutStages(steps: Step[], g: Geometry): { nodes: Node[]; bands: Band[]; height: number } {
  const ordered: Omit<Node, 'x' | 'y'>[] = [{ id: 'ask', stage: 'ask', step: null, synthetic: 'ask' }];
  const handedOff = steps.some((s) => s.kind === 'agent');
  let keptAdded = false;
  for (const s of steps) {
    const stage = stageOf(s);
    // No handoff means the supervisor did the work itself; say so where a specialist would be.
    if (!handedOff && !keptAdded && (stage === 'work' || stage === 'knowledge')) {
      ordered.push({ id: 'kept', stage: 'agent', step: null, synthetic: 'kept' });
      keptAdded = true;
    }
    ordered.push({ id: s.key, stage, step: s });
  }
  ordered.push({ id: 'answer', stage: 'answer', step: null, synthetic: 'answer' });

  const perRow = Math.max(1, Math.floor((g.width - g.labelW - g.pad + g.gapX) / (g.nodeW + g.gapX)));
  const bands: Band[] = [];
  const nodes: Node[] = [];
  let y = g.pad;
  for (const stage of STAGES) {
    const inBand = ordered.filter((n) => n.stage === stage);
    if (inBand.length === 0) continue;
    const rows = Math.ceil(inBand.length / perRow);
    const h = rows * g.nodeH + (rows - 1) * g.gapY + g.pad * 2;
    bands.push({ stage, y, h });
    inBand.forEach((n, i) => {
      const row = Math.floor(i / perRow);
      const col = i % perRow;
      nodes.push({ ...n, x: g.labelW + col * (g.nodeW + g.gapX), y: y + g.pad + row * (g.nodeH + g.gapY) });
    });
    y += h;
  }
  // Back to path order for drawing connectors.
  const byId = new Map(nodes.map((n) => [n.id, n]));
  return { nodes: ordered.map((n) => byId.get(n.id)!), bands, height: y + g.pad };
}
