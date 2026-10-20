'use client';

import { AlertOctagon, AlertTriangle, CheckCircle2, Eye } from 'lucide-react';
import { formatMoney } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { DeficitSeverity } from '@/lib/types';

import { useWorkspace } from '@/lib/workspace';

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <header className="flex flex-col gap-4 pb-8 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </header>
  );
}

export function SectionTitle({ children, aside }: { children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <h2 className="shrink-0 text-base font-semibold">{children}</h2>
      {aside && <div className="text-sm text-muted-foreground">{aside}</div>}
    </div>
  );
}

export function Money({ value, currency, signed, cents, className }: { value: string; currency?: string; signed?: boolean; cents?: boolean; className?: string }) {
  const { homeCurrency, source, live } = useWorkspace();
  const effectiveCurrency = currency ?? (source === 'live' ? (live.analysis?.currency ?? homeCurrency) : homeCurrency);
  return <span className={cn('figures whitespace-nowrap', className)}>{formatMoney(value, effectiveCurrency, { signed, cents })}</span>;
}

const SEVERITY = {
  SAFE: { icon: CheckCircle2, cls: 'text-good-text bg-good/10' },
  WATCH: { icon: Eye, cls: 'text-ink-2 bg-muted' },
  WARNING: { icon: AlertTriangle, cls: 'text-warning-text bg-warning/15' },
  CRITICAL: { icon: AlertOctagon, cls: 'text-critical-text bg-critical/10' },
} as const;

export function SeverityBadge({ severity, className }: { severity: DeficitSeverity; className?: string }) {
  const s = SEVERITY[severity];
  const { t } = useT();
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium', s.cls, className)}>
      <s.icon className="size-3.5" aria-hidden />
      {t(`sev.${severity}`)}
    </span>
  );
}

const TIERS = {
  1: 'bg-muted text-ink-2',
  2: 'bg-accent text-accent-foreground',
  3: 'bg-warning/15 text-warning-text',
} as const;

export function TierBadge({ tier }: { tier: 1 | 2 | 3 }) {
  const { t } = useT();
  return <span className={cn('inline-flex rounded-full px-2 py-0.5 text-xs font-medium', TIERS[tier])}>{t(`tier.${tier}`)}</span>;
}
