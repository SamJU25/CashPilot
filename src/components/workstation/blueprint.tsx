'use client';

import { useEffect, useId, useMemo, useState } from 'react';
import { useReducedMotion } from 'motion/react';
import { useT, type Key } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import type { RecordedRun } from '@/lib/runs';
import {
  AGENT_TOOLS,
  DECISION_DOMAINS,
  ENGINE_LABEL,
  knowledgeFiles,
  LANES,
  engineFamily,
  formatMs,
  humanize,
  linksOf,
  stepsOf,
  zoneOf,
  type EngineFamily,
  type Lane,
  type Link,
  type Step,
  type Zone,
} from './model';

type T = (k: Key, v?: Record<string, string | number>) => string;
type Agent = Exclude<Lane, 'supervisor'>;

// The sheet: a three-column grid (knowledge | system | decision engine) over an observability row.
const W = 1000;
const LX = 16, LW = 180; // left column
const CX = 216, CW = 548; // centre column
const RX = 784, RW = 200; // right column
const SUP_Y = 16, SUP_H = 134;
const SUB_Y = 60, SUB_H = 78, SUB_W = 122, SUB_GAP = 12;
const AG_Y = 186, AG_W = 176, AG_GAP = 10, ROW = 28;
const KN_Y = 160, KN_ROW = 20;
const BUS_X = 206, GUT_X = 774, KN_CH = 168, EN_CH = 176;
const STEP_MS = 220; // playback pace; the times printed are the real ones
const PULSE_MS = 520;

const AGENTS = LANES.slice(1) as Agent[];
const agentX = (a: Agent) => CX + AGENTS.indexOf(a) * (AG_W + AG_GAP);
const SUBS: Exclude<Zone, Agent>[] = ['guard', 'intent', 'persona', 'direct'];
const subX = (i: number) => CX + 12 + i * (SUB_W + SUB_GAP);

const COLOR: Record<Lane, string> = {
  supervisor: 'rgb(var(--ink-2))',
  liquidity: 'rgb(var(--s3))',
  credit: 'rgb(var(--s1))',
  risk: 'rgb(var(--s2))',
};
const PRIMARY = 'rgb(var(--primary))';
const FAINT = 'rgb(var(--border))';

const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
function wrap(s: string, n: number, lines: number) {
  const out: string[] = [];
  let line = '';
  for (const w of s.split(/\s+/)) {
    if (line && (line + ' ' + w).length > n) {
      out.push(line);
      line = w;
    } else line = line ? `${line} ${w}` : w;
  }
  if (line) out.push(line);
  return out.length > lines ? [...out.slice(0, lines - 1), clip(out.slice(lines - 1).join(' '), n)] : out;
}

const decisionName = (s: Step, t: T) => {
  const k = `wk.d.${s.name}`;
  const named = t(k as Key);
  return named === k ? humanize(s.name) : named;
};
const labelOf = (s: Step, t: T) => (s.kind === 'decision' ? decisionName(s, t) : s.kind === 'tool' ? humanize(s.name) : s.name);

function Glyph({ kind, x, y, color }: { kind: Step['kind']; x: number; y: number; color: string }) {
  if (kind === 'decision') return <rect x={x - 4.5} y={y - 4.5} width={9} height={9} transform={`rotate(45 ${x} ${y})`} fill="rgb(var(--card))" stroke={color} strokeWidth={1.4} />;
  if (kind === 'tool')
    return (
      <g>
        <rect x={x - 4.5} y={y - 4.5} width={9} height={9} fill="rgb(var(--card))" stroke={color} strokeWidth={1.4} />
        <path d={`M ${x - 7.5} ${y - 4.5} h 2 M ${x + 5.5} ${y - 4.5} h 2 M ${x - 7.5} ${y + 4.5} h 2 M ${x + 5.5} ${y + 4.5} h 2`} stroke={color} strokeWidth={1} />
      </g>
    );
  if (kind === 'card') return <rect x={x - 5.5} y={y - 4} width={11} height={8} rx={1.2} fill="rgb(var(--card))" stroke={color} strokeWidth={1.2} strokeDasharray="2 1.4" />;
  return <circle cx={x} cy={y} r={4.5} fill="rgb(var(--card))" stroke={color} strokeWidth={1.4} />;
}

/** Click and keyboard handling for anything on the map that opens a step's detail. */
const hit = (key: string | undefined, onSelect: (k: string) => void, label: string) =>
  key
    ? {
        role: 'button' as const,
        tabIndex: 0,
        'aria-label': label,
        className: 'cursor-pointer',
        onClick: () => onSelect(key),
        onKeyDown: (e: React.KeyboardEvent) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onSelect(key)),
      }
    : {};

/** A panel header: title, a muted subtitle and a state on the right. */
function Head({ x, y, w, title, sub, state, color }: { x: number; y: number; w: number; title: string; sub?: string; state?: string; color?: string }) {
  return (
    <g>
      {color && <rect x={x} y={y} width={w} height={3} rx={1.5} fill={color} />}
      <text x={x + 12} y={y + 22} className="fill-foreground font-display text-[13.5px] font-semibold">
        {title}
      </text>
      {sub && (
        <text x={x + 12} y={y + 37} className="fill-muted-foreground text-[10.5px]">
          {sub}
        </text>
      )}
      {state && (
        <text x={x + w - 12} y={y + 22} textAnchor="end" className="fill-muted-foreground text-[10.5px]">
          {state}
        </text>
      )}
    </g>
  );
}

/** One step as a chip inside a panel: glyph, name, time. */
function Chip({ s, x, y, w, color, lit, selected, onSelect, t }: { s: Step; x: number; y: number; w: number; color: string; lit: boolean; selected: boolean; onSelect: (k: string) => void; t: T }) {
  const label = labelOf(s, t) + (s.count > 1 ? ` ×${s.count}` : '');
  return (
    <g {...hit(s.key, onSelect, label)} opacity={lit ? 1 : 0} style={{ transition: 'opacity 200ms' }}>
      <title>{`${label}\n${formatMs(s.duration)}`}</title>
      <rect x={x} y={y} width={w} height={22} rx={4} fill={selected ? 'rgb(var(--accent))' : 'rgb(var(--card))'} stroke={selected ? PRIMARY : FAINT} strokeWidth={selected ? 1.4 : 1} />
      <Glyph kind={s.kind} x={x + 12} y={y + 11} color={color} />
      <text x={x + 23} y={y + 15} className="fill-foreground text-[11px]">
        {clip(label, Math.floor((w - 70) / 5.6))}
      </text>
      <text x={x + w - 7} y={y + 15} textAnchor="end" className="fill-muted-foreground font-mono text-[9px]">
        {formatMs(s.duration)}
      </text>
    </g>
  );
}

export function Blueprint({ run, selected, onSelect, playKey }: { run: RecordedRun; selected: string | null; onSelect: (key: string) => void; playKey: number }) {
  const { t } = useT();
  const reduce = useReducedMotion();
  const uid = useId().replace(/:/g, '');
  const steps = useMemo(() => stepsOf(run.trace), [run]);
  const links = useMemo(() => linksOf(steps), [steps]);
  const end = steps.length + 1;
  const [shown, setShown] = useState(end);

  // Playback walks the run step by step; reduced motion shows the finished map.
  useEffect(() => {
    if (reduce) {
      setShown(end);
      return;
    }
    setShown(1);
    let i = 1;
    const id = window.setInterval(() => {
      i += 1;
      setShown(i);
      if (i >= end) window.clearInterval(id);
    }, STEP_MS);
    return () => window.clearInterval(id);
  }, [end, playKey, reduce]);

  const idx = new Map(steps.map((s, i) => [s.key, i]));
  const lit = (s: Step) => (idx.get(s.key) ?? 0) < shown;
  const inZone = (z: Zone) => steps.filter((s) => s.kind !== 'agent' && zoneOf(s) === z);
  const current = shown < end ? steps[shown - 1] : undefined;
  const done = shown >= end;

  const agentState = (a: Agent | 'supervisor') => {
    const handoff = a === 'supervisor' ? 0 : steps.findIndex((s) => s.kind === 'agent' && s.lane === a);
    if (handoff < 0) return 'unused';
    if (handoff >= shown) return 'waiting';
    return current && current.lane === a ? 'working' : done ? 'done' : 'waiting';
  };

  const files = knowledgeFiles(steps);
  const rows = Math.min(6, Math.max(5, ...AGENTS.map((a) => inZone(a).length)));
  // Agent panels stretch so the knowledge list always fits beside them, however many card files exist.
  const AG_H = Math.max(50 + rows * ROW + 8, KN_Y + 48 + files.length * KN_ROW + 8 - AG_Y);
  const agBottom = AG_Y + AG_H;
  const ANS_Y = agBottom + 30;
  const ANS_H = 46;
  const BOT_Y = ANS_Y + ANS_H + 30;
  const BOT_H = 112;
  const H = BOT_Y + BOT_H + 16;
  const blocked = run.intent === 'SECURITY_DEFENSE_TRIGGERED';

  /* ---- Connectors: orthogonal traces between panels. */
  const zoneAnchor = (z: Zone) => (SUBS.includes(z as never) ? null : agentX(z as Agent));
  const pathOf = (l: Link): string => {
    if (l.kind === 'ask') return `M ${LX + LW} ${SUB_Y + SUB_H / 2} H ${subX(0) - 3}`;
    if (l.kind === 'handoff') {
      const x = agentX(l.to as Agent) + AG_W / 2;
      return `M ${x} ${SUP_Y + SUP_H} V ${AG_Y - 3}`;
    }
    if (l.kind === 'knowledge') {
      const used = files.map((f, i) => (steps.some((s) => s.kind === 'card' && s.detail.file === f && zoneOf(s) === l.to) ? i : -1)).filter((i) => i >= 0);
      const low = KN_Y + 48 + Math.max(0, ...used) * KN_ROW + KN_ROW / 2;
      const ax = zoneAnchor(l.to as Zone);
      return ax === null ? `M ${BUS_X} ${low} V ${SUP_Y + SUP_H - 20} H ${CX - 3}` : `M ${BUS_X} ${low} V ${KN_CH} H ${ax + 30} V ${AG_Y - 3}`;
    }
    if (l.kind === 'engine') {
      const ax = zoneAnchor(l.to as Zone);
      return ax === null ? `M ${RX} ${SUP_Y + 24} H ${CX + CW + 3}` : `M ${RX} ${EN_CH} H ${ax + AG_W - 26} V ${AG_Y - 3}`;
    }
    const from = l.from && zoneAnchor(l.from);
    return from == null ? `M ${CX + CW} ${SUP_Y + SUP_H - 20} H ${GUT_X} V ${ANS_Y + 14} H ${CX + CW + 3}` : `M ${from + AG_W / 2} ${agBottom} V ${ANS_Y - 3}`;
  };
  const badgeAt = (l: Link): [number, number] => {
    if (l.kind === 'ask') return [BUS_X, SUB_Y + SUB_H / 2];
    if (l.kind === 'handoff') return [agentX(l.to as Agent) + AG_W / 2, KN_CH];
    if (l.kind === 'knowledge') return zoneAnchor(l.to as Zone) === null ? [BUS_X, SUP_Y + SUP_H - 20] : [BUS_X, KN_CH];
    const from = l.from && zoneAnchor(l.from);
    return from == null ? [GUT_X, (SUP_Y + SUP_H + ANS_Y) / 2] : [from + AG_W / 2, (agBottom + ANS_Y) / 2];
  };
  const linkColor = (l: Link) => (l.kind === 'handoff' ? COLOR[l.to as Agent] : l.kind === 'knowledge' ? 'rgb(var(--s4))' : l.kind === 'engine' ? 'rgb(var(--ink-2))' : PRIMARY);
  const linkLit = (l: Link) => l.at < shown;

  // The wiring every run could use, drawn faint so the system reads as a whole.
  const wiring = [
    `M ${LX + LW} ${SUB_Y + SUB_H / 2} H ${subX(0)}`,
    ...AGENTS.map((a) => `M ${agentX(a) + AG_W / 2} ${SUP_Y + SUP_H} V ${AG_Y}`),
    ...AGENTS.map((a) => `M ${agentX(a) + AG_W / 2} ${agBottom} V ${ANS_Y}`),
    `M ${CX + CW} ${SUP_Y + SUP_H - 20} H ${GUT_X} V ${ANS_Y + 14} H ${CX + CW}`,
  ];

  /* ---- Decision engine tallies. */
  const decisions = steps.filter((s) => s.kind === 'decision');
  const tally = (f: EngineFamily) => decisions.filter((s) => engineFamily(s) === f && lit(s)).reduce((n, s) => n + s.count, 0);
  const domains = [...new Set(decisions.map((s) => s.name))].map((name) => {
    const all = decisions.filter((s) => s.name === name);
    return { name, first: all[0], n: all.reduce((n, s) => n + s.count, 0) };
  });
  const enRows = Math.floor((agBottom - SUP_Y - 196) / 20);

  /* ---- Observability: every step on one clock. */
  const t0 = Math.min(...run.trace.map((e) => e.start_ms), 0);
  const t1 = Math.max(...steps.map((s) => s.start + s.duration), 1);
  const OX = LX + 120, OW = CX + CW - 16 - OX;
  const ox = (ms: number) => OX + ((ms - t0) / (t1 - t0)) * OW;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full min-w-[820px]" role="img" aria-label={t('wk.figAria', { n: steps.length })}>
      <defs>
        <pattern id={`${uid}-g`} width={10} height={10} patternUnits="userSpaceOnUse">
          <path d="M 10 0 H 0 V 10" fill="none" stroke="rgb(var(--primary) / 0.06)" strokeWidth={0.5} />
        </pattern>
        <pattern id={`${uid}-G`} width={50} height={50} patternUnits="userSpaceOnUse">
          <rect width={50} height={50} fill={`url(#${uid}-g)`} />
          <path d="M 50 0 H 0 V 50" fill="none" stroke="rgb(var(--primary) / 0.11)" strokeWidth={0.75} />
        </pattern>
        <marker id={`${uid}-a`} viewBox="0 0 8 8" refX={6} refY={4} markerWidth={6} markerHeight={6} orient="auto-start-reverse">
          <path d="M 0 0.5 L 7 4 L 0 7.5 z" fill="context-stroke" />
        </marker>
      </defs>
      <rect width={W} height={H} fill={`url(#${uid}-G)`} />

      {wiring.map((d, i) => (
        <path key={i} d={d} fill="none" stroke={FAINT} strokeWidth={1} />
      ))}

      {/* ---- Question */}
      <g>
        <rect x={LX} y={SUP_Y} width={LW} height={SUB_Y + SUB_H - SUP_Y} rx={8} fill="rgb(var(--card))" stroke={PRIMARY} strokeWidth={1.2} />
        <Head x={LX} y={SUP_Y} w={LW} title={t('wk.map.question')} />
        {wrap(`“${run.question}”`, 27, 4).map((line, i) => (
          <text key={i} x={LX + 12} y={SUP_Y + 44 + i * 16} className="fill-foreground text-[11.5px]">
            {line}
          </text>
        ))}
      </g>

      {/* ---- Supervisor: the brain, with its four stations */}
      <g>
        <rect x={CX} y={SUP_Y} width={CW} height={SUP_H} rx={10} fill="rgb(var(--card) / 0.92)" stroke={agentState('supervisor') === 'working' ? PRIMARY : 'rgb(var(--primary) / 0.45)'} strokeWidth={1.2} />
        <Head x={CX} y={SUP_Y} w={CW} title={t('wk.lane.supervisor')} sub={t('wk.map.supervisorSub')} state={t(`wk.state.${agentState('supervisor')}` as Key)} />
        {SUBS.map((z, i) => {
          const zs = inZone(z);
          const x = subX(i);
          const reached = zs.some(lit);
          const last = zs.filter(lit).at(-1);
          const isSel = zs.some((s) => s.key === selected);
          const total = zs.reduce((n, s) => n + s.count, 0);
          const engine = last?.detail.engine ? ENGINE_LABEL(last.detail.engine) : '';
          const stop = z === 'guard' && blocked && reached;
          return (
            <g key={z} {...hit(zs[0]?.key, onSelect, t(`wk.map.${z}` as Key))}>
              {i > 0 && <path d={`M ${x - SUB_GAP} ${SUB_Y + SUB_H / 2} H ${x - 3}`} stroke={reached ? PRIMARY : FAINT} strokeWidth={1.2} markerEnd={`url(#${uid}-a)`} />}
              <rect x={x} y={SUB_Y} width={SUB_W} height={SUB_H} rx={6} fill={isSel ? 'rgb(var(--accent))' : 'rgb(var(--background) / 0.6)'} stroke={stop ? 'rgb(var(--critical))' : reached ? PRIMARY : FAINT} strokeWidth={reached ? 1.3 : 1} strokeDasharray={zs.length ? undefined : '3 3'} />
              <text x={x + 10} y={SUB_Y + 17} className="fill-muted-foreground text-[10px] font-medium uppercase tracking-wide">
                {t(`wk.map.${z}` as Key)}
              </text>
              {z !== 'direct' ? (
                last ? (
                  <>
                    <text x={x + 10} y={SUB_Y + 39} className={cn('font-display text-[14px] font-semibold', stop ? 'fill-critical-text' : 'fill-foreground')}>
                      {clip(humanize(last.detail.choice ?? ''), 15)}
                    </text>
                    <text x={x + 10} y={SUB_Y + 56} className="fill-muted-foreground text-[10px]">
                      {engine ? t(`${engine}Short` as Key) : ''}
                      {total > 1 ? `  ×${total}` : ''}
                    </text>
                    <text x={x + 10} y={SUB_Y + 71} className="fill-muted-foreground font-mono text-[9px]">
                      {formatMs(zs.reduce((n, s) => n + s.duration, 0))}
                    </text>
                  </>
                ) : (
                  <text x={x + 10} y={SUB_Y + 39} className="fill-muted-foreground text-[11px]">
                    {zs.length ? '…' : t('wk.map.notReached')}
                  </text>
                )
              ) : zs.length ? (
                <>
                  {zs.slice(0, 2).map((s, k) => (
                    <g key={s.key} opacity={lit(s) ? 1 : 0} style={{ transition: 'opacity 200ms' }}>
                      <Glyph kind={s.kind} x={x + 15} y={SUB_Y + 34 + k * 18} color={COLOR.supervisor} />
                      <text x={x + 26} y={SUB_Y + 38 + k * 18} className="fill-foreground text-[10.5px]">
                        {clip(labelOf(s, t), 15)}
                      </text>
                    </g>
                  ))}
                  {zs.length > 2 && (
                    <text x={x + 10} y={SUB_Y + 74} className="fill-muted-foreground text-[10px]">
                      {t('wk.map.more', { n: zs.length - 2 })}
                    </text>
                  )}
                </>
              ) : (
                <text x={x + 10} y={SUB_Y + 39} className="fill-muted-foreground text-[11px]">
                  {steps.some((s) => s.kind === 'agent') ? t('wk.map.handedOn') : t('wk.map.notReached')}
                </text>
              )}
            </g>
          );
        })}
      </g>

      {/* ---- Subagents */}
      {AGENTS.map((a) => {
        const x = agentX(a);
        const state = agentState(a);
        const zs = inZone(a);
        const shownItems = zs.length > rows ? zs.slice(0, rows - 1) : zs;
        return (
          <g key={a} opacity={state === 'unused' ? 0.62 : 1}>
            <rect x={x} y={AG_Y} width={AG_W} height={AG_H} rx={8} fill="rgb(var(--card) / 0.92)" stroke={state === 'working' ? COLOR[a] : state === 'unused' ? FAINT : `rgb(var(--${a === 'liquidity' ? 's3' : a === 'credit' ? 's1' : 's2'}) / 0.55)`} strokeWidth={state === 'working' ? 1.6 : 1.1} strokeDasharray={state === 'unused' ? '4 3' : undefined} />
            <Head x={x} y={AG_Y} w={AG_W} title={t(`wk.lane.${a}` as Key)} sub={t(`wk.map.${a}Sub` as Key)} state={t(`wk.state.${state}` as Key)} color={COLOR[a]} />
            {state === 'unused' ? (
              <g>
                <text x={x + 12} y={AG_Y + 64} className="fill-muted-foreground text-[10.5px]">
                  {t('wk.map.toolsHas', { n: AGENT_TOOLS[a].count })}
                </text>
                {AGENT_TOOLS[a].examples.map((name, k) => (
                  <g key={name}>
                    <rect x={x + 10} y={AG_Y + 74 + k * ROW} width={AG_W - 20} height={22} rx={4} fill="none" stroke={FAINT} strokeDasharray="3 2" />
                    <Glyph kind="tool" x={x + 22} y={AG_Y + 85 + k * ROW} color={FAINT} />
                    <text x={x + 33} y={AG_Y + 89 + k * ROW} className="fill-muted-foreground text-[10.5px]">
                      {clip(humanize(name), 21)}
                    </text>
                  </g>
                ))}
              </g>
            ) : (
              <g>
                {shownItems.map((s, k) => (
                  <g key={s.key}>
                    {k > 0 && <path d={`M ${x + 22} ${AG_Y + 50 + (k - 1) * ROW + 22} V ${AG_Y + 50 + k * ROW}`} stroke={lit(s) ? COLOR[a] : 'transparent'} strokeWidth={1} />}
                    <Chip s={s} x={x + 10} y={AG_Y + 50 + k * ROW} w={AG_W - 20} color={COLOR[a]} lit={lit(s)} selected={selected === s.key} onSelect={onSelect} t={t} />
                  </g>
                ))}
                {zs.length > shownItems.length && (
                  <text x={x + 12} y={AG_Y + 50 + shownItems.length * ROW + 15} className="fill-muted-foreground text-[10.5px]" opacity={lit(zs[shownItems.length]) ? 1 : 0}>
                    {t('wk.map.more', { n: zs.length - shownItems.length })}
                  </text>
                )}
                {zs.length === 0 && state !== 'waiting' && (
                  <text x={x + 12} y={AG_Y + 64} className="fill-muted-foreground text-[10.5px]">
                    {t('wk.map.reasoned')}
                  </text>
                )}
              </g>
            )}
          </g>
        );
      })}

      {/* ---- Knowledge layer */}
      <g>
        <rect x={LX} y={KN_Y} width={LW} height={agBottom - KN_Y} rx={8} fill="rgb(var(--card) / 0.92)" stroke="rgb(var(--s4) / 0.55)" strokeWidth={1.1} />
        <Head x={LX} y={KN_Y} w={LW} title={t('wk.map.knowledge')} sub={t('wk.map.files', { n: files.length })} color="rgb(var(--s4))" />
        {files.map((f, i) => {
          const cards = steps.filter((s) => s.kind === 'card' && s.detail.file === f);
          const on = cards.some(lit);
          const y = KN_Y + 48 + i * KN_ROW;
          return (
            <g key={f} {...hit(cards[0]?.key, onSelect, f)}>
              {on && <rect x={LX + 6} y={y} width={LW - 12} height={KN_ROW - 2} rx={3} fill={cards.some((c) => c.key === selected) ? 'rgb(var(--accent))' : 'rgb(var(--s4) / 0.12)'} />}
              <path d={`M ${LX + 14} ${y + 4} h 6 l 3 3 v 8 h -9 z`} fill="none" stroke={on ? 'rgb(var(--s4))' : FAINT} strokeWidth={1} />
              <text x={LX + 30} y={y + 13} className={cn('font-mono text-[10px]', on ? 'fill-foreground' : 'fill-muted-foreground')}>
                {clip(f.replace(/\.md$/, ''), 22)}
              </text>
              {on && (
                <>
                  <text x={LX + LW - 12} y={y + 13} textAnchor="end" className="fill-foreground font-mono text-[10px]">
                    {cards.filter(lit).length}
                  </text>
                  <path d={`M ${LX + LW} ${y + KN_ROW / 2 - 1} H ${BUS_X}`} stroke="rgb(var(--s4))" strokeWidth={1.2} />
                </>
              )}
            </g>
          );
        })}
      </g>

      {/* ---- Decision engine */}
      <g>
        <rect x={RX} y={SUP_Y} width={RW} height={agBottom - SUP_Y} rx={8} fill="rgb(var(--card) / 0.92)" stroke="rgb(var(--ink-2) / 0.45)" strokeWidth={1.1} />
        <Head x={RX} y={SUP_Y} w={RW} title={t('wk.map.engine')} sub={t('wk.map.domains', { n: DECISION_DOMAINS })} color="rgb(var(--ink-2))" />
        {(['rules', 'model', 'fallback'] as EngineFamily[]).map((f, i) => {
          const y = SUP_Y + 50 + i * 36;
          const n = tally(f);
          return (
            <g key={f}>
              <rect x={RX + 10} y={y} width={RW - 20} height={30} rx={5} fill={n ? 'rgb(var(--ink-2) / 0.08)' : 'none'} stroke={n ? 'rgb(var(--ink-2) / 0.5)' : FAINT} />
              <text x={RX + 20} y={y + 13} className={cn('text-[11px] font-medium', n ? 'fill-foreground' : 'fill-muted-foreground')}>
                {t(`wk.engine.${f}` as Key)}
              </text>
              <text x={RX + 20} y={y + 24} className="fill-muted-foreground font-mono text-[8.5px]">
                {f === 'rules' ? 'zen-engine' : f === 'model' ? 'system-one@onnx' : t('wk.map.fallbackWhen')}
              </text>
              <text x={RX + RW - 20} y={y + 20} textAnchor="end" className={cn('figures font-display text-[16px] font-semibold', n ? 'fill-foreground' : 'fill-muted-foreground')}>
                {n}
              </text>
            </g>
          );
        })}
        <text x={RX + 12} y={SUP_Y + 172} className="fill-muted-foreground text-[10px] font-medium uppercase tracking-wide">
          {t('wk.map.decided')}
        </text>
        {domains.slice(0, enRows).map((d, i) => {
          const y = SUP_Y + 180 + i * 20;
          return (
            <g key={d.name} {...hit(d.first.key, onSelect, decisionName(d.first, t))} opacity={lit(d.first) ? 1 : 0} style={{ transition: 'opacity 200ms' }}>
              {selected && domains[i].first.key === selected && <rect x={RX + 6} y={y} width={RW - 12} height={18} rx={3} fill="rgb(var(--accent))" />}
              <Glyph kind="decision" x={RX + 18} y={y + 9} color={COLOR[d.first.lane]} />
              <text x={RX + 30} y={y + 13} className="fill-foreground text-[10.5px]">
                {clip(decisionName(d.first, t), 22)}
              </text>
              <text x={RX + RW - 12} y={y + 13} textAnchor="end" className="fill-muted-foreground font-mono text-[9.5px]">
                ×{d.n}
              </text>
            </g>
          );
        })}
        {domains.length > enRows && (
          <text x={RX + 12} y={SUP_Y + 180 + enRows * 20 + 12} className="fill-muted-foreground text-[10px]">
            {t('wk.map.more', { n: domains.length - enRows })}
          </text>
        )}
      </g>

      {/* ---- Answer */}
      <g opacity={done ? 1 : 0.55} style={{ transition: 'opacity 200ms' }}>
        <rect x={CX} y={ANS_Y} width={CW} height={ANS_H} rx={8} fill="rgb(var(--card))" stroke={done ? (blocked ? 'rgb(var(--critical))' : PRIMARY) : FAINT} strokeWidth={1.2} />
        <circle cx={CX + 22} cy={ANS_Y + ANS_H / 2} r={7} fill="none" stroke={done ? PRIMARY : FAINT} strokeWidth={1.4} />
        <path d={`M ${CX + 18.5} ${ANS_Y + ANS_H / 2} l 2.2 2.2 4.3 -4.3`} fill="none" stroke={done ? PRIMARY : FAINT} strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
        <text x={CX + 40} y={ANS_Y + 20} className="fill-foreground font-display text-[13.5px] font-semibold">
          {t('wk.map.answer')}
        </text>
        <text x={CX + 40} y={ANS_Y + 35} className="fill-muted-foreground text-[10.5px]">
          {done ? (blocked ? t('wk.nd.blocked') : t('wk.answeredAs', { intent: humanize(run.intent) })) : '…'}
        </text>
        <text x={CX + CW - 12} y={ANS_Y + 28} textAnchor="end" className="fill-muted-foreground font-mono text-[10px]">
          {done ? formatMs(t1 - t0) : ''}
        </text>
      </g>

      {/* ---- Observability: the run on one clock, a row per agent */}
      <g>
        <rect x={LX} y={BOT_Y} width={CX + CW - LX} height={BOT_H} rx={8} fill="rgb(var(--card) / 0.92)" stroke={FAINT} />
        <Head x={LX} y={BOT_Y} w={CX + CW - LX} title={t('wk.map.observe')} state={t('wk.map.observeSub', { n: steps.length, ms: formatMs(t1 - t0) })} />
        {LANES.map((lane, r) => {
          const y = BOT_Y + 38 + r * 17;
          return (
            <g key={lane}>
              <text x={LX + 12} y={y + 9} className="fill-muted-foreground text-[10px]">
                {t(`wk.lane.${lane}` as Key)}
              </text>
              <line x1={OX} x2={OX + OW} y1={y + 5} y2={y + 5} stroke={FAINT} strokeDasharray="1 3" />
              {steps
                .filter((s) => s.lane === lane)
                .map((s) => (
                  <rect
                    key={s.key}
                    {...hit(s.key, onSelect, labelOf(s, t))}
                    x={ox(s.start)}
                    y={y}
                    width={Math.max(2.5, ox(s.start + s.duration) - ox(s.start))}
                    height={10}
                    rx={2}
                    fill={COLOR[lane]}
                    opacity={lit(s) ? (selected === s.key ? 1 : 0.8) : 0}
                    stroke={selected === s.key ? PRIMARY : 'none'}
                    style={{ transition: 'opacity 200ms' }}
                  >
                    <title>{`${labelOf(s, t)}  ${formatMs(s.duration)}`}</title>
                  </rect>
                ))}
            </g>
          );
        })}
      </g>

      {/* ---- Human handoff: where drafts go; the owner sends them */}
      <g>
        <path d={`M ${CX + CW} ${ANS_Y + 34} H ${RX + RW / 2} V ${BOT_Y - 3}`} fill="none" stroke={FAINT} strokeDasharray="4 3" markerEnd={`url(#${uid}-a)`} />
        <rect x={RX} y={BOT_Y} width={RW} height={BOT_H} rx={8} fill="rgb(var(--card) / 0.92)" stroke="rgb(var(--warning) / 0.5)" strokeDasharray="4 3" />
        <Head x={RX} y={BOT_Y} w={RW} title={t('wk.map.handoff')} />
        {wrap(t('wk.map.handoffBody'), 30, 4).map((line, i) => (
          <text key={i} x={RX + 12} y={BOT_Y + 44 + i * 15} className="fill-muted-foreground text-[10.5px]">
            {line}
          </text>
        ))}
      </g>

      {/* ---- The run's path: drawn as the signal reaches each connector, numbered in order */}
      {links.map((l) => {
        if (!linkLit(l)) return null;
        const d = pathOf(l);
        const color = linkColor(l);
        const dashed = l.kind === 'knowledge' || l.kind === 'engine';
        return (
          <g key={`${l.id}-${playKey}`}>
            <path d={d} fill="none" stroke={color} strokeWidth={dashed ? 1.2 : 1.6} strokeDasharray={dashed ? (l.kind === 'engine' ? '2 3' : '5 3') : undefined} markerEnd={`url(#${uid}-a)`} />
            {!reduce &&
              [0, 1, 2].map((k) => (
                <circle key={k} r={2.8 - k * 0.6} fill={color} className="wk-pulse" style={{ offsetPath: `path("${d}")`, animationDelay: `${k * 80}ms`, animationDuration: `${PULSE_MS}ms` }} />
              ))}
          </g>
        );
      })}
      {links.map((l) => {
        if (!l.n || !linkLit(l)) return null;
        const [x, y] = badgeAt(l);
        return (
          <g key={`b-${l.id}`}>
            <circle cx={x} cy={y} r={8} fill="rgb(var(--card))" stroke={linkColor(l)} strokeWidth={1.3} />
            <text x={x} y={y + 3.5} textAnchor="middle" className="fill-foreground font-mono text-[9.5px] font-semibold">
              {l.n}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
