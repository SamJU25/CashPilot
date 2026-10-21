'use client';

import { useState } from 'react';
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';

interface CalendarPickerProps {
  id?: string;
  value: string; // ISO date 'YYYY-MM-DD'
  onChange: (date: string) => void;
  className?: string;
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const DAY_LABELS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

export function CalendarPicker({ id, value, onChange, className }: CalendarPickerProps) {
  const [open, setOpen] = useState(false);

  // Parse initial year and month
  const initialDate = value && !isNaN(Date.parse(value)) ? new Date(`${value}T00:00:00Z`) : new Date();
  const [viewYear, setViewYear] = useState(() => initialDate.getUTCFullYear());
  const [viewMonth, setViewMonth] = useState(() => initialDate.getUTCMonth());

  const prevMonth = () => {
    if (viewMonth === 0) {
      setViewMonth(11);
      setViewYear((y) => y - 1);
    } else {
      setViewMonth((m) => m - 1);
    }
  };

  const nextMonth = () => {
    if (viewMonth === 11) {
      setViewMonth(0);
      setViewYear((y) => y + 1);
    } else {
      setViewMonth((m) => m + 1);
    }
  };

  const daysInMonth = new Date(Date.UTC(viewYear, viewMonth + 1, 0)).getUTCDate();
  const firstDayOfWeek = new Date(Date.UTC(viewYear, viewMonth, 1)).getUTCDay();
  const prevMonthDays = new Date(Date.UTC(viewYear, viewMonth, 0)).getUTCDate();

  const handleSelectDay = (day: number) => {
    const mm = String(viewMonth + 1).padStart(2, '0');
    const dd = String(day).padStart(2, '0');
    const iso = `${viewYear}-${mm}-${dd}`;
    onChange(iso);
    setOpen(false);
  };

  const selectToday = () => {
    const today = new Date();
    const iso = today.toISOString().slice(0, 10);
    setViewYear(today.getUTCFullYear());
    setViewMonth(today.getUTCMonth());
    onChange(iso);
    setOpen(false);
  };

  const todayIso = new Date().toISOString().slice(0, 10);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          className={cn(
            'h-9 w-full justify-start text-left font-mono text-xs font-normal bg-card/60 border-input/60 hover:bg-accent/40 shadow-2xs gap-2 px-3',
            className
          )}
        >
          <CalendarIcon className="h-3.5 w-3.5 text-primary shrink-0" />
          <span className="truncate">{value ? formatDate(value, true) : 'Select date'}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        sideOffset={6}
        className="w-[270px] p-3 rounded-xl border border-border/80 bg-popover text-popover-foreground shadow-xl"
      >
        {/* Month/Year Header */}
        <div className="flex items-center justify-between pb-2 mb-2 border-b border-border/40">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={prevMonth}
            className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
            aria-label="Previous Month"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-xs font-semibold text-foreground">
            {MONTH_NAMES[viewMonth]} {viewYear}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={nextMonth}
            className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
            aria-label="Next Month"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        {/* Days of Week Row */}
        <div className="grid grid-cols-7 gap-1 text-center mb-1">
          {DAY_LABELS.map((d) => (
            <span key={d} className="text-[10px] font-semibold text-muted-foreground select-none">
              {d}
            </span>
          ))}
        </div>

        {/* Days Grid */}
        <div className="grid grid-cols-7 gap-1 text-center font-mono text-xs figures">
          {/* Leading empty days from prev month */}
          {Array.from({ length: firstDayOfWeek }).map((_, i) => {
            const dayNum = prevMonthDays - firstDayOfWeek + i + 1;
            return (
              <span key={`prev-${i}`} className="h-7 flex items-center justify-center text-muted-foreground/30 text-[11px] select-none">
                {dayNum}
              </span>
            );
          })}

          {/* Current month days */}
          {Array.from({ length: daysInMonth }).map((_, i) => {
            const day = i + 1;
            const mm = String(viewMonth + 1).padStart(2, '0');
            const dd = String(day).padStart(2, '0');
            const currentIso = `${viewYear}-${mm}-${dd}`;
            const isSelected = value === currentIso;
            const isToday = todayIso === currentIso;

            return (
              <button
                key={`day-${day}`}
                type="button"
                onClick={() => handleSelectDay(day)}
                className={cn(
                  'h-7 w-full rounded-md flex items-center justify-center transition-colors text-xs font-medium',
                  isSelected
                    ? 'bg-primary text-primary-foreground font-semibold shadow-2xs'
                    : isToday
                      ? 'border border-primary/50 text-primary hover:bg-primary/10'
                      : 'text-foreground hover:bg-accent hover:text-accent-foreground'
                )}
              >
                {day}
              </button>
            );
          })}
        </div>

        {/* Footer shortcuts */}
        <div className="pt-2 mt-2 border-t border-border/40 flex items-center justify-between">
          <button
            type="button"
            onClick={selectToday}
            className="text-[11px] font-medium text-primary hover:underline underline-offset-2"
          >
            Today ({todayIso})
          </button>
          <span className="text-[10px] text-muted-foreground font-mono">
            {value}
          </span>
        </div>
      </PopoverContent>
    </Popover>
  );
}
