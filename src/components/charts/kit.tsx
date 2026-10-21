'use client';

import { useId } from 'react';
import { motion } from 'motion/react';
import { spring, STAGGER_S } from '@/lib/motion';
import { cn } from '@/lib/utils';

/* Small hand-drawn SVG charts shared by every page. Marks are thin, data ends are rounded, and each
   chart draws in once; MotionConfig turns the movement off for reduced-motion users. */

const draw = { duration: 0.6, ease: [0.16, 1, 0.3, 1] } as const;

/** A half-circle gauge: value on a 0..max arc, with an optional threshold tick. */
export function Gauge({
  value,
  max,
  threshold,
  tone,
  children,
  label,
}: {
  value: number;
  max: number;
  threshold?: number;
  tone: string;
  children?: React.ReactNode;
  label: string;
}) {
  const R = 80;
  const C = Math.PI * R;
  const frac = Math.max(0, Math.min(1, value / max));
  const tick = threshold !== undefined ? Math.max(0, Math.min(1, threshold / max)) : null;
  const at = (f: number, r: number) => [100 - Math.cos(Math.PI * f) * r, 100 - Math.sin(Math.PI * f) * r] as const;
  return (
    <div className="relative mx-auto w-full max-w-[15rem]">
      <svg viewBox="0 0 200 112" className="w-full" role="img" aria-label={label}>
        <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="rgb(var(--muted))" strokeWidth={12} strokeLinecap="round" />
        <motion.path
          d="M20 100 A80 80 0 0 1 180 100"
          fill="none"
          className={tone}
          stroke="currentColor"
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={C}
          initial={{ strokeDashoffset: C }}
          animate={{ strokeDashoffset: C * (1 - frac) }}
          transition={draw}
        />
        {tick !== null && (
          <line
            x1={at(tick, 66)[0]}
            y1={at(tick, 66)[1]}
            x2={at(tick, 94)[0]}
            y2={at(tick, 94)[1]}
            stroke="rgb(var(--foreground))"
            strokeWidth={2}
            strokeLinecap="round"
          />
        )}
      </svg>
      <div className="absolute inset-x-0 bottom-0 flex flex-col items-center">{children}</div>
    </div>
  );
}

export interface Segment {
  key: string;
  label: string;
  value: number;
  color: string;
}

/** Part-to-whole ring, up to six segments, with a 2px gap between them and the total in the middle. */
export function Donut({ segments, children, label, size = 168 }: { segments: Segment[]; children?: React.ReactNode; label: string; size?: number }) {
  const R = 42;
  const C = 2 * Math.PI * R;
  const total = segments.reduce((s, x) => s + Math.max(0, x.value), 0) || 1;
  const gap = segments.filter((s) => s.value > 0).length > 1 ? 1.6 : 0;
  let offset = 0;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" className="-rotate-90" width={size} height={size} role="img" aria-label={label}>
        <circle cx={50} cy={50} r={R} fill="none" stroke="rgb(var(--muted))" strokeWidth={10} />
        {segments
          .filter((s) => s.value > 0)
          .map((s, i) => {
            const len = (s.value / total) * C;
            const dash = Math.max(0, len - gap);
            const el = (
              <motion.circle
                key={s.key}
                cx={50}
                cy={50}
                r={R}
                fill="none"
                stroke={s.color}
                strokeWidth={10}
                strokeDasharray={`${dash} ${C - dash}`}
                strokeDashoffset={-offset}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ ...draw, delay: i * STAGGER_S * 2 }}
              >
                <title>{s.label}</title>
              </motion.circle>
            );
            offset += len;
            return el;
          })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">{children}</div>
    </div>
  );
}

/** Legend for a Donut: swatch, label, value; identity never rests on colour alone. */
export function Legend({ segments, format }: { segments: Segment[]; format: (v: number) => string }) {
  const total = segments.reduce((s, x) => s + Math.max(0, x.value), 0) || 1;
  return (
    <ul className="w-full space-y-2 text-sm">
      {segments.map((s) => (
        <li key={s.key} className="flex items-center gap-2.5">
          <span className="size-2.5 shrink-0 rounded-sm" style={{ background: s.color }} aria-hidden />
          <span className="min-w-0 flex-1 truncate text-ink-2">{s.label}</span>
          <span className="figures font-medium">{format(s.value)}</span>
          <span className="figures w-9 text-right text-xs text-muted-foreground">{Math.round((s.value / total) * 100)}%</span>
        </li>
      ))}
    </ul>
  );
}

/** Filled line for a single series, the latest point marked. */
export function MiniArea({ values, className, label }: { values: number[]; className?: string; label: string }) {
  const rawId = useId();
  const fillId = 'mini-area-' + rawId.replace(/:/g, '');
  if (values.length < 2) return null;
  const W = 160;
  const H = 44;
  const min = Math.min(...values);
  const span = Math.max(...values) - min || 1;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * W, H - 4 - ((v - min) / span) * (H - 8)] as const);
  const line = `M${pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join('L')}`;
  const [lx, ly] = pts[pts.length - 1];
  // The SVG stretches to its box, so the line keeps a screen-pixel stroke and is revealed with a wipe:
  // pathLength dashes would be measured in stretched units and leave the line half drawn.
  return (
    <div className={cn('relative h-11 w-full text-primary', className)} role="img" aria-label={label}>
      <motion.svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full overflow-visible"
        initial={{ clipPath: 'inset(0 100% 0 0)' }}
        animate={{ clipPath: 'inset(0 0% 0 0)' }}
        transition={draw}
        aria-hidden
      >
        <defs>
          <linearGradient id={fillId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="currentColor" stopOpacity={0.22} />
            <stop offset="100%" stopColor="currentColor" stopOpacity={0} />
          </linearGradient>
        </defs>
        <path d={`${line}L${W},${H}L0,${H}Z`} fill={`url(#${fillId})`} />
        <path d={line} fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      </motion.svg>
      {/* An HTML dot stays round however the SVG is stretched. */}
      <span
        className="absolute size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-current ring-2 ring-card"
        style={{ left: `${(lx / W) * 100}%`, top: `${(ly / H) * 100}%` }}
        aria-hidden
      />
    </div>
  );
}

/** Columns around a zero line: up in the accent, down in a warm contrast, each with a native tooltip. */
export function MiniBars({ values, titles, label }: { values: number[]; titles: string[]; label: string }) {
  const max = Math.max(1, ...values.map(Math.abs));
  return (
    <div className="flex h-11 items-center gap-[3px]" role="img" aria-label={label}>
      {values.map((v, i) => {
        const h = Math.max(2, (Math.abs(v) / max) * 50);
        return (
          <div key={i} className="relative h-full flex-1" title={titles[i]}>
            <span className="absolute inset-x-0 top-1/2 h-px bg-border" aria-hidden />
            <motion.span
              className={cn('absolute inset-x-0 rounded-[2px]', v >= 0 ? 'bg-primary' : 'bg-serious')}
              style={v >= 0 ? { bottom: '50%', height: `${h}%`, originY: 1 } : { top: '50%', height: `${h}%`, originY: 0 }}
              initial={{ scaleY: 0 }}
              animate={{ scaleY: 1 }}
              transition={{ ...spring.gentle, delay: i * STAGGER_S }}
            />
          </div>
        );
      })}
    </div>
  );
}

/** Two values compared on one scale, as stacked horizontal bars. */
export function CompareBars({ rows }: { rows: { label: string; value: number; display: string; tone: string }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="space-y-2.5">
      {rows.map((r, i) => (
        <div key={r.label}>
          <div className="flex items-baseline justify-between gap-2 text-xs">
            <span className="text-muted-foreground">{r.label}</span>
            <span className="figures font-medium text-foreground">{r.display}</span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-muted">
            <motion.div
              className={cn('h-full rounded-full', r.tone)}
              style={{ width: `${(r.value / max) * 100}%`, originX: 0 }}
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ ...spring.gentle, delay: i * STAGGER_S }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

/** A 0..100 score as a small closed ring with the number inside. */
export function ScoreRing({ value, tone = 'text-primary', size = 44, label }: { value: number; tone?: string; size?: number; label: string }) {
  const R = 16;
  const C = 2 * Math.PI * R;
  const frac = Math.max(0, Math.min(1, value / 100));
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={label}>
      <svg viewBox="0 0 40 40" width={size} height={size} className="-rotate-90">
        <circle cx={20} cy={20} r={R} fill="none" stroke="rgb(var(--muted))" strokeWidth={4} />
        <motion.circle
          cx={20}
          cy={20}
          r={R}
          fill="none"
          className={tone}
          stroke="currentColor"
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={C}
          initial={{ strokeDashoffset: C }}
          animate={{ strokeDashoffset: C * (1 - frac) }}
          transition={draw}
        />
      </svg>
      <span className="figures absolute inset-0 flex items-center justify-center text-xs font-semibold">{Math.round(value)}</span>
    </div>
  );
}
