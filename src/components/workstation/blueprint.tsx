'use client';

import { useEffect, useId, useMemo, useState } from 'react';
import { useReducedMotion } from 'motion/react';
import { useT, type Key } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import type { RecordedRun } from '@/lib/runs';
import { ENGINE_LABEL, LANES, formatMs, humanize, layoutStages, stepsOf, usedLanes, type Lane, type Node, type Stage, type Step } from './model';

// A fixed 840-wide sheet that scales to its frame.
const G = { width: 840, labelW: 118, nodeW: 158, nodeH: 46, gapX: 14, gapY: 14, pad: 16 };
const HEAD = 64; // agent status row
const STEP_MS = 260; // playback pace, in path order; the times printed are the real ones
const PULSE_MS = 480;

// Agents keep one colour everywhere (categorical slots in fixed order); the supervisor stays neutral.
const AGENT_COLOR: Record<Lane, string> = {
  supervisor: 'rgb(var(--ink-2))',
  liquidity: 'rgb(var(--s3))',
  credit: 'rgb(var(--s1))',
  risk: 'rgb(var(--s2))',
};

const STAGE_KEY: Record<Stage, Key> = {
  ask: 'wk.sg.ask',
  guard: 'wk.sg.guard',
  route: 'wk.sg.route',
  agent: 'wk.sg.agent',
  work: 'wk.sg.work',
  knowledge: 'wk.sg.knowledge',
  answer: 'wk.sg.answer',
};

const wide = (n: Node) => n.synthetic === 'ask' || n.synthetic === 'answer';
const nodeW = (n: Node) => (wide(n) ? G.nodeW * 2 + G.gapX : G.nodeW);
const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** A trace between two nodes: along a row, down between stages, or looping out when the run goes back up. */
function trace(a: Node, b: Node) {
  const ay = a.y + HEAD;
  const by = b.y + HEAD;
  const aw = nodeW(a);
  if (Math.abs(ay - by) < 1 && b.x > a.x) return `M ${a.x + aw} ${ay + G.nodeH / 2} L ${b.x - 6} ${by + G.nodeH / 2}`;
  if (by > ay) {
    const x1 = a.x + Math.min(aw, G.nodeW) / 2;
    const x2 = b.x + Math.min(nodeW(b), G.nodeW) / 2;
    const y1 = ay + G.nodeH;
    const y2 = by - 6;
    const my = (y1 + y2) / 2;
    return `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`;
  }
  // Back up to an earlier stage: leave to the right and re-enter from the right, like a feedback loop.
  const xa = a.x + aw;
  const xb = b.x + nodeW(b);
  const out = Math.max(xa, xb) + 26;
  return `M ${xa} ${ay + G.nodeH / 2} C ${out} ${ay + G.nodeH / 2}, ${out} ${by + G.nodeH / 2}, ${xb + 6} ${by + G.nodeH / 2}`;
}

function Glyph({ kind, x, y, color }: { kind: Step['kind'] | 'ask' | 'answer' | 'kept'; x: number; y: number; color: string }) {
  if (kind === 'decision') return <rect x={x - 6} y={y - 6} width={12} height={12} transform={`rotate(45 ${x} ${y})`} fill="rgb(var(--card))" stroke={color} strokeWidth={1.5} />;
  if (kind === 'tool')
    return (
      <g>
        <rect x={x - 6} y={y - 6} width={12} height={12} fill="rgb(var(--card))" stroke={color} strokeWidth={1.5} />
        <path d={`M ${x - 10} ${y - 6} h 2.5 M ${x + 7.5} ${y - 6} h 2.5 M ${x - 10} ${y + 6} h 2.5 M ${x + 7.5} ${y + 6} h 2.5`} stroke={color} strokeWidth={1} />
      </g>
    );
  if (kind === 'card') return <rect x={x - 7} y={y - 5} width={14} height={10} rx={1.5} fill="rgb(var(--card))" stroke={color} strokeWidth={1.25} strokeDasharray="2.5 1.5" />;
  if (kind === 'ask' || kind === 'answer')
    return (
      <g>
        <circle cx={x} cy={y} r={6.5} fill="rgb(var(--card))" stroke={color} strokeWidth={1.5} />
        <path d={kind === 'ask' ? `M ${x - 2.5} ${y} h 5 M ${x + 0.5} ${y - 2.5} l 2.5 2.5 -2.5 2.5` : `M ${x - 3} ${y} l 2 2 4 -4`} fill="none" stroke={color} strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
      </g>
    );
  return (
    <g>
      <circle cx={x} cy={y} r={6.5} fill="rgb(var(--card))" stroke={color} strokeWidth={1.5} />
      <circle cx={x} cy={y} r={2.2} fill={color} />
    </g>
  );
}

function textFor(n: Node, run: RecordedRun, t: (k: Key, v?: Record<string, string | number>) => string) {
  if (n.synthetic === 'ask') return { title: t('wk.nd.ask'), sub: `“${run.question}”` };
  if (n.synthetic === 'answer') return { title: t('wk.nd.answer'), sub: run.intent === 'SECURITY_DEFENSE_TRIGGERED' ? t('wk.nd.blocked') : humanize(run.intent) };
  if (n.synthetic === 'kept') return { title: t('wk.nd.kept'), sub: t('wk.nd.keptSub') };
  const s = n.step!;
  if (s.kind === 'decision') {
    const k = `wk.d.${s.name}`;
    const named = t(k as Key);
    const title = named === k ? humanize(s.name) : named;
    const engine = ENGINE_LABEL(s.detail.engine);
    return { title: s.count > 1 ? `${title} ×${s.count}` : title, sub: `${engine ? t(`${engine}Short` as Key) : ''} → ${humanize(s.detail.choice ?? '')}`, time: formatMs(s.duration) };
  }
  if (s.kind === 'tool') return { title: humanize(s.name), sub: `${s.name}()`, mono: true, time: formatMs(s.duration) };
  if (s.kind === 'card') return { title: s.name, sub: t('wk.cardFrom', { file: s.detail.file ?? '', score: s.detail.score ?? '' }) };
  return { title: t('wk.handoff', { agent: t(`wk.lane.${s.name}` as Key) }), sub: t('wk.nd.handoffSub'), time: formatMs(s.duration) };
}

export function Blueprint({ run, selected, onSelect, playKey }: { run: RecordedRun; selected: string | null; onSelect: (key: string) => void; playKey: number }) {
  const { t } = useT();
  const reduce = useReducedMotion();
  const uid = useId().replace(/:/g, '');
  const steps = useMemo(() => stepsOf(run.trace), [run]);
  const used = useMemo(() => usedLanes(steps), [steps]);
  const { nodes, bands, height } = useMemo(() => layoutStages(steps, G), [steps]);
  const [shown, setShown] = useState(reduce ? nodes.length : 0);

  // Playback walks the signal path one node at a time; reduced motion shows the finished drawing.
  useEffect(() => {
    if (reduce) {
      setShown(nodes.length);
      return;
    }
    setShown(1);
    let i = 1;
    const id = window.setInterval(() => {
      i += 1;
      setShown(i);
      if (i >= nodes.length) window.clearInterval(id);
    }, STEP_MS);
    return () => window.clearInterval(id);
  }, [nodes, playKey, reduce]);

  const H = HEAD + height;
  const done = shown >= nodes.length;
  const current = !done ? nodes[shown - 1] : undefined;
  const laneOfNode = (n: Node): Lane => n.step?.lane ?? 'supervisor';
  const laneState = (lane: Lane) => {
    if (!used.has(lane)) return 'unused';
    if (!nodes.slice(0, shown).some((n) => n.step?.lane === lane || (lane === 'supervisor' && !n.step))) return 'waiting';
    return current && laneOfNode(current) === lane ? 'working' : done ? 'done' : 'waiting';
  };

  return (
    <svg viewBox={`0 0 ${G.width} ${H}`} className="block w-full min-w-[660px]" role="img" aria-label={t('wk.figAria', { n: steps.length })}>
      <defs>
        <pattern id={`${uid}-g`} width={12} height={12} patternUnits="userSpaceOnUse">
          <path d="M 12 0 H 0 V 12" fill="none" stroke="rgb(var(--primary) / 0.07)" strokeWidth={0.5} />
        </pattern>
        <pattern id={`${uid}-G`} width={60} height={60} patternUnits="userSpaceOnUse">
          <rect width={60} height={60} fill={`url(#${uid}-g)`} />
          <path d="M 60 0 H 0 V 60" fill="none" stroke="rgb(var(--primary) / 0.12)" strokeWidth={0.75} />
        </pattern>
        <marker id={`${uid}-arrow`} viewBox="0 0 8 8" refX={6} refY={4} markerWidth={7} markerHeight={7} orient="auto-start-reverse">
          <path d="M 0 0.5 L 7 4 L 0 7.5 z" fill="rgb(var(--primary))" />
        </marker>
      </defs>
      <rect width={G.width} height={H} fill={`url(#${uid}-G)`} />

      {/* Agent status row: each agent's colour and what it is doing now. */}
      {LANES.map((lane, i) => {
        const state = laneState(lane);
        const x = 16 + i * 204;
        return (
          <g key={lane} opacity={state === 'unused' ? 0.45 : 1}>
            <rect x={x} y={14} width={192} height={36} rx={6} fill="rgb(var(--card))" stroke={state === 'working' ? AGENT_COLOR[lane] : 'rgb(var(--border))'} strokeWidth={state === 'working' ? 1.5 : 1} />
            <rect x={x} y={14} width={4} height={36} rx={2} fill={AGENT_COLOR[lane]} />
            <text x={x + 16} y={36} className="fill-foreground font-display text-[13.5px] font-semibold">
              {t(`wk.lane.${lane}` as Key)}
            </text>
            <text x={x + 180} y={36} textAnchor="end" className={cn('text-[11px]', state === 'working' ? 'fill-primary' : 'fill-muted-foreground')}>
              {t(`wk.state.${state}` as Key)}
            </text>
          </g>
        );
      })}

      {/* Stage bands with their numbered labels: the order a request passes through. */}
      {bands.map((b, i) => (
        <g key={b.stage}>
          {i > 0 && <line x1={16} x2={G.width - 16} y1={HEAD + b.y} y2={HEAD + b.y} stroke="rgb(var(--primary) / 0.18)" strokeDasharray="3 4" />}
          <text x={16} y={HEAD + b.y + G.pad + 17} className="fill-primary font-mono text-[10.5px]">
            {String(i + 1).padStart(2, '0')}
          </text>
          <text x={36} y={HEAD + b.y + G.pad + 17} className="fill-foreground font-display text-[13px] font-semibold">
            {t(STAGE_KEY[b.stage])}
          </text>
        </g>
      ))}

      {/* Traces: drawn when the signal reaches the next node; the pulse runs once and the trace stays lit. */}
      {nodes.map((n, i) => {
        if (i === 0 || i >= shown) return null;
        const d = trace(nodes[i - 1], n);
        return (
          <g key={`c-${n.id}-${playKey}`}>
            <path d={d} fill="none" stroke="rgb(var(--primary) / 0.6)" strokeWidth={1.3} markerEnd={`url(#${uid}-arrow)`} className="wk-draw" style={{ animationDuration: reduce ? '0ms' : `${PULSE_MS}ms` }} pathLength={1} />
            {!reduce &&
              [0, 1, 2].map((k) => (
                <circle key={k} r={2.6 - k * 0.55} className="wk-pulse fill-primary" style={{ offsetPath: `path("${d}")`, animationDelay: `${k * 75}ms`, animationDuration: `${PULSE_MS}ms` }} />
              ))}
          </g>
        );
      })}

      {/* Nodes: an instrument card per step, coloured by the agent that ran it. */}
      {nodes.map((n, i) => {
        const visible = i < shown;
        const working = current?.id === n.id;
        const lane = laneOfNode(n);
        const color = n.synthetic ? 'rgb(var(--primary))' : AGENT_COLOR[lane];
        const w = nodeW(n);
        const y = n.y + HEAD;
        const txt = textFor(n, run, t);
        const isSel = !!n.step && selected === n.step.key;
        const chars = wide(n) ? 48 : 19;
        return (
          <g
            key={n.id}
            className={cn('transition-opacity duration-200', visible ? 'opacity-100' : 'opacity-0', n.step && 'cursor-pointer')}
            onClick={() => n.step && onSelect(n.step.key)}
            onKeyDown={(e) => n.step && (e.key === 'Enter' || e.key === ' ') && onSelect(n.step.key)}
            role={n.step ? 'button' : undefined}
            tabIndex={n.step && visible ? 0 : -1}
            aria-label={`${txt.title}. ${txt.sub}`}
          >
            <title>{`${txt.title}\n${txt.sub}${txt.time ? `\n${txt.time}` : ''}`}</title>
            <rect
              x={n.x}
              y={y}
              width={w}
              height={G.nodeH}
              rx={6}
              fill={isSel ? 'rgb(var(--accent))' : 'rgb(var(--card))'}
              stroke={working || isSel ? 'rgb(var(--primary))' : 'rgb(var(--border))'}
              strokeWidth={working || isSel ? 1.5 : 1}
            />
            <rect x={n.x} y={y + 8} width={3} height={G.nodeH - 16} rx={1.5} fill={color} />
            <Glyph kind={n.synthetic ?? n.step!.kind} x={n.x + 18} y={y + G.nodeH / 2} color={color} />
            <text x={n.x + 32} y={y + 19} className="fill-foreground text-[12px] font-medium">
              {clip(txt.title, chars)}
            </text>
            <text x={n.x + 32} y={y + 34} className={cn('fill-muted-foreground text-[10.5px]', txt.mono && 'font-mono text-[10px]')}>
              {clip(txt.sub, wide(n) ? 54 : 24)}
            </text>
            {txt.time && (
              <text x={n.x + w - 8} y={y + 19} textAnchor="end" className="fill-muted-foreground font-mono text-[9.5px]">
                {txt.time}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
