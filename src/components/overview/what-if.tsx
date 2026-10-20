'use client';

import { AnimatePresence, motion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { formatDate, formatMoney } from '@/lib/format';
import { fade, spring } from '@/lib/motion';
import type { Projection, Scenario } from '@/lib/mock/demo';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';

function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn('relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors', checked ? 'bg-primary' : 'bg-input')}
    >
      <motion.span layout transition={spring.snappy} className={cn('size-4 rounded-full bg-card shadow-sm', checked ? 'ml-[18px]' : 'ml-0.5')} />
    </button>
  );
}

function Range({ id, label, value, min, max, step, display, onChange }: { id: string; label: string; value: number; min: number; max: number; step: number; display: string; onChange: (v: number) => void }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-sm">
          {label}
        </label>
        <output htmlFor={id} className="figures text-sm font-medium">
          {display}
        </output>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2 h-1.5 w-full cursor-pointer accent-[rgb(var(--primary))]"
      />
    </div>
  );
}

function daysBetween(a: string, b: string) {
  return Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000);
}

/** The invoice-collection lever, when there is a known overdue amount: label and the assumption it makes. */
export interface CollectLever {
  label: string;
  note: string;
}

export function WhatIf({
  scenario,
  onChange,
  base,
  result,
  collect,
}: {
  scenario: Scenario;
  onChange: (s: Scenario) => void;
  base: Projection;
  result: Projection;
  collect: CollectLever | null;
}) {
  const { t } = useT();
  const changed = scenario.cutPct > 0 || scenario.extraMonthlyCents > 0 || scenario.collectInvoice;
  const r = result.forecast;
  const b = base.forecast;

  let headline: string;
  let detail: string;
  if (!changed) {
    headline = t('whatif.try');
    detail = t('whatif.tryBody');
  } else if (!r.has_projected_deficit) {
    headline = t('whatif.none');
    detail = t('whatif.noneBody');
  } else {
    const shift = b.projected_deficit_date ? daysBetween(b.projected_deficit_date, r.projected_deficit_date!) : 0;
    const amount = formatMoney(r.projected_shortfall_amount);
    headline = t('whatif.on', { date: formatDate(r.projected_deficit_date!) });
    detail = shift > 0 ? t('whatif.later', { n: shift, amount }) : shift < 0 ? t('whatif.sooner', { n: -shift, amount }) : t('whatif.same', { amount });
  }

  return (
    <section aria-labelledby="what-if-title" className="flex h-full flex-col">
      <h2 id="what-if-title" className="text-base font-semibold">
        {t('whatif.title')}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">{t('whatif.sub')}</p>

      <div className="mt-6 space-y-6">
        {collect && (
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm">{collect.label}</p>
              <p className="text-xs text-muted-foreground">{collect.note}</p>
            </div>
            <Switch checked={scenario.collectInvoice} onChange={(v) => onChange({ ...scenario, collectInvoice: v })} label={collect.label} />
          </div>
        )}
        <Range
          id="cut"
          label={t('whatif.cut')}
          value={scenario.cutPct}
          min={0}
          max={30}
          step={5}
          display={`${scenario.cutPct}%`}
          onChange={(v) => onChange({ ...scenario, cutPct: v })}
        />
        <Range
          id="extra"
          label={t('whatif.extra')}
          value={scenario.extraMonthlyCents / 100}
          min={0}
          max={10000}
          step={500}
          display={formatMoney(String(scenario.extraMonthlyCents / 100), undefined, { cents: false })}
          onChange={(v) => onChange({ ...scenario, extraMonthlyCents: v * 100 })}
        />
      </div>

      <div className="mt-auto pt-6">
        <div className="rounded-md bg-muted/60 p-4" aria-live="polite">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={headline + detail} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={fade}>
              <p className={cn('text-sm font-medium', changed && !r.has_projected_deficit && 'text-good-text')}>{headline}</p>
              <p className="mt-0.5 text-sm text-muted-foreground">{detail}</p>
            </motion.div>
          </AnimatePresence>
        </div>
        {changed && (
          <Button variant="ghost" size="sm" className="mt-2 px-2 text-ink-2" onClick={() => onChange({ cutPct: 0, extraMonthlyCents: 0, collectInvoice: false })}>
            {t('whatif.reset')}
          </Button>
        )}
      </div>
    </section>
  );
}
