'use client';

import { useEffect, useRef, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { formatDate } from '@/lib/format';
import { todayIso } from '@/lib/live-forecast';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';

// Dates stay ISO strings handled in UTC, so no time zone can shift the chosen day.
const parse = (iso: string) => new Date(`${iso}T00:00:00Z`);
const iso = (d: Date) => d.toISOString().slice(0, 10);
const addDays = (s: string, n: number) => {
  const d = parse(s);
  d.setUTCDate(d.getUTCDate() + n);
  return iso(d);
};
const addMonths = (s: string, n: number) => {
  const d = parse(s);
  const day = d.getUTCDate();
  d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() + n);
  d.setUTCDate(Math.min(day, new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate()));
  return iso(d);
};

/** A themed calendar in a popover; the browser's own date picker cannot follow the app's colours or type. */
export function DatePicker({ id, value, onChange, max, className }: { id?: string; value: string; onChange: (v: string) => void; max?: string; className?: string }) {
  const { t, lang } = useT();
  const [open, setOpen] = useState(false);
  const [focus, setFocus] = useState(value);
  const grid = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) setFocus(value);
  }, [open, value]);
  // Keyboard moves the focused day; keep real focus on it so screen readers follow.
  useEffect(() => {
    if (open) grid.current?.querySelector<HTMLButtonElement>(`[data-day="${focus}"]`)?.focus();
  }, [focus, open]);

  // English calendars start on Sunday; the other languages offered start on Monday.
  const weekStart = lang.startsWith('en') ? 0 : 1;
  const view = parse(focus);
  const first = new Date(Date.UTC(view.getUTCFullYear(), view.getUTCMonth(), 1));
  const lead = (first.getUTCDay() - weekStart + 7) % 7;
  const daysInMonth = new Date(Date.UTC(view.getUTCFullYear(), view.getUTCMonth() + 1, 0)).getUTCDate();
  const cells = Array.from({ length: Math.ceil((lead + daysInMonth) / 7) * 7 }, (_, i) => addDays(iso(first), i - lead));
  const monthLabel = new Intl.DateTimeFormat(lang, { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(first);
  const weekday = new Intl.DateTimeFormat(lang, { weekday: 'narrow', timeZone: 'UTC' });
  const dayLabel = new Intl.DateTimeFormat(lang, { dateStyle: 'full', timeZone: 'UTC' });
  const today = todayIso();
  const disabled = (d: string) => !!max && d > max;

  const pick = (d: string) => {
    if (disabled(d)) return;
    onChange(d);
    setOpen(false);
  };
  const onKey = (e: React.KeyboardEvent) => {
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key];
    if (step) setFocus((f) => addDays(f, step));
    else if (e.key === 'PageUp') setFocus((f) => addMonths(f, -1));
    else if (e.key === 'PageDown') setFocus((f) => addMonths(f, 1));
    else return;
    e.preventDefault();
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          className={cn(
            'flex h-10 w-full items-center gap-2 rounded-md border border-input bg-background px-3 text-left text-sm transition-colors hover:border-ink-2/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            className,
          )}
        >
          <CalendarDays className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <span className="figures truncate">{formatDate(value, true)}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-[18rem] p-3"
        // Start on the chosen day, not the first button, so arrow keys work at once.
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          grid.current?.querySelector<HTMLButtonElement>(`[data-day="${value}"]`)?.focus();
        }}
      >
        <div className="mb-2 flex items-center justify-between">
          <button type="button" onClick={() => setFocus((f) => addMonths(f, -1))} className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground" aria-label={t('cal.prev')}>
            <ChevronLeft className="size-4" aria-hidden />
          </button>
          <p className="font-display text-base font-semibold" aria-live="polite">
            {monthLabel}
          </p>
          <button type="button" onClick={() => setFocus((f) => addMonths(f, 1))} className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground" aria-label={t('cal.next')}>
            <ChevronRight className="size-4" aria-hidden />
          </button>
        </div>
        <div className="grid grid-cols-7 text-center text-[11px] text-muted-foreground" aria-hidden>
          {cells.slice(0, 7).map((d) => (
            <span key={d} className="py-1">
              {weekday.format(parse(d))}
            </span>
          ))}
        </div>
        <div ref={grid} role="grid" aria-label={monthLabel} onKeyDown={onKey} className="grid grid-cols-7 gap-0.5">
          {cells.map((d) => {
            const inMonth = parse(d).getUTCMonth() === view.getUTCMonth();
            const selected = d === value;
            return (
              <button
                key={d}
                type="button"
                role="gridcell"
                data-day={d}
                tabIndex={d === focus ? 0 : -1}
                aria-selected={selected}
                aria-label={dayLabel.format(parse(d))}
                disabled={disabled(d)}
                onClick={() => pick(d)}
                className={cn(
                  'figures flex h-9 items-center justify-center rounded-md text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  selected ? 'bg-primary font-semibold text-primary-foreground' : 'hover:bg-muted',
                  !selected && d === today && 'font-semibold text-primary ring-1 ring-inset ring-primary/50',
                  !inMonth && !selected && 'text-muted-foreground/50',
                  'disabled:pointer-events-none disabled:opacity-30',
                )}
              >
                {parse(d).getUTCDate()}
              </button>
            );
          })}
        </div>
        <div className="mt-2 flex justify-end border-t pt-2">
          <button type="button" onClick={() => pick(max && today > max ? max : today)} className="rounded-md px-2 py-1 text-xs font-medium text-primary hover:bg-muted">
            {t('cal.today')}
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
