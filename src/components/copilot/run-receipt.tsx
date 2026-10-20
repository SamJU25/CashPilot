'use client';

import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Check, ChevronDown } from 'lucide-react';
import { fade, spring } from '@/lib/motion';
import { cn } from '@/lib/utils';
import type { AgentId, RunStep } from '@/lib/types';
import { useT, type Key } from '@/lib/i18n';
import { useWorkspace } from '@/lib/workspace';

const AGENT_DOT: Record<AgentId, string> = {
  supervisor: 'bg-muted-foreground',
  liquidity: 'bg-series-3',
  credit: 'bg-series-1',
  risk: 'bg-series-2',
};

// Real identifiers for the technical view: subagent classes in services/agent/subagents/.
const AGENT_CLASS: Record<AgentId, string> = {
  supervisor: 'supervisor',
  liquidity: 'LiquiditySubagent',
  credit: 'CreditSubagent',
  risk: 'RiskManagerSubagent',
};

const chip = 'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs text-ink-2';

/** Plain layer: who did the step and with what, in words an owner reads at a glance. */
function Chips({ step }: { step: RunStep }) {
  const { t } = useT();
  if (!step.agent && !step.tool && !step.card) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {step.agent && (
        <span className={chip}>
          <span className={cn('size-1.5 rounded-full', AGENT_DOT[step.agent])} aria-hidden />
          {t(`agent.${step.agent}` as Key)}
        </span>
      )}
      {step.tool && <span className={chip}>{t(`tool.${step.tool}` as Key)}</span>}
      {step.card && (
        <span className={chip}>
          {t('rc.card', {
            name: t(`card.${step.card.slug}` as Key) === `card.${step.card.slug}` ? step.card.title : t(`card.${step.card.slug}` as Key),
          })}
        </span>
      )}
    </div>
  );
}

/** Technical layer: the real class, function and card names with timings. */
function TechLine({ step }: { step: RunStep }) {
  const parts = [
    step.agent && step.tool ? `${AGENT_CLASS[step.agent]} → ${step.tool}()` : step.agent ? AGENT_CLASS[step.agent] : step.tool ? `${step.tool}()` : null,
    step.card ? `knowledge/cards/${step.card.file} § ${step.card.title}` : null,
    step.tech ?? null,
    `${step.duration_ms} ms`,
  ].filter(Boolean);
  return <p className="mt-1.5 break-words font-mono text-xs leading-5 text-muted-foreground">{parts.join(' · ')}</p>;
}

function totalMs(steps: RunStep[]) {
  const ms = steps.reduce((s, x) => s + x.duration_ms, 0);
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`;
}

/** Collapsed: one line summary. Expanded: every step with its inputs and, where math ran, the formula. */
export function RunReceipt({ steps, defaultOpen = false, live = 0, holdOpen = false }: { steps: RunStep[]; defaultOpen?: boolean; live?: number; holdOpen?: boolean }) {
  const [userOpen, setOpen] = useState(defaultOpen);
  const { t } = useT();
  const { techDetails, update } = useWorkspace();
  const shown = live > 0 ? steps.slice(0, live) : steps;
  const running = live > 0 && live < steps.length;
  // While working the steps stay visible (they replace the old reasoning stream); once done they fold to one line.
  const open = running || holdOpen || userOpen;

  return (
    <div className="text-xs">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-md py-1 text-left text-ink-2 hover:text-foreground"
      >
        <span className={cn('flex size-4 items-center justify-center rounded-full', running ? 'border border-primary' : 'bg-primary text-primary-foreground')} aria-hidden>
          {!running && <Check className="size-3" strokeWidth={3} />}
        </span>
        <span className="flex-1">
          {running ? t('receipt.working', { i: live, n: steps.length }) : t('receipt.steps', { n: steps.length, time: totalMs(steps) })}
        </span>
        <ChevronDown className={cn('size-4 transition-transform duration-200', open && 'rotate-180')} aria-hidden />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={spring.smooth}
            className="overflow-hidden"
          >
            <div className="flex justify-end pt-1">
              <button
                type="button"
                role="switch"
                aria-checked={techDetails}
                onClick={() => update({ techDetails: !techDetails })}
                className="flex items-center gap-2 rounded-md px-1.5 py-1 text-xs text-muted-foreground hover:text-foreground"
              >
                <span className={cn('relative inline-flex h-3.5 w-6 items-center rounded-full transition-colors', techDetails ? 'bg-primary' : 'bg-input')} aria-hidden>
                  <span className={cn('size-2.5 rounded-full bg-card shadow-sm transition-transform duration-150', techDetails ? 'translate-x-3' : 'translate-x-0.5')} />
                </span>
                {t('rc.tech')}
              </button>
            </div>
            <ol>
              {shown.map((step, i) => (
                <motion.li
                  key={`${i}-${step.label}`}
                  initial={live ? { opacity: 0 } : false}
                  animate={{ opacity: 1 }}
                  transition={fade}
                  className="relative grid grid-cols-[16px_1fr] gap-x-3 pb-4 pt-2 last:pb-1"
                >
                  {i < shown.length - 1 && <span className="absolute left-[7.5px] top-6 h-[calc(100%-12px)] w-px bg-border" aria-hidden />}
                  <span className="relative mt-1 size-2 justify-self-center rounded-full bg-primary/70" aria-hidden />
                  <div>
                    <p className="font-medium text-foreground">{step.label}</p>
                    <p className="text-muted-foreground">{step.detail}</p>
                    {techDetails ? <TechLine step={step} /> : <Chips step={step} />}
                    {step.formula && <pre className="mt-2 overflow-x-auto rounded bg-muted px-3 py-2 font-mono text-xs leading-5 text-ink-2">{step.formula}</pre>}
                  </div>
                </motion.li>
              ))}
            </ol>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
