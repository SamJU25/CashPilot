'use client';

import { Info } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Money } from '@/components/common/bits';
import { formatDate, formatMoney } from '@/lib/format';
import { useT } from '@/lib/i18n';
import type { CashAnalysis } from '@/lib/types';

interface Figure {
  label: string;
  value: string;
  note: string;
  how: string;
  formula: string;
}

export function KeyFigures({ analysis }: { analysis: CashAnalysis }) {
  const a = analysis;
  const { t } = useT();
  const transfers = formatMoney(a.internal_transfers_excluded ?? '0');
  const figures: Figure[] = [
    {
      label: t('fig.cash'),
      value: a.current_balance,
      note: t('fig.cashNote', { n: a.accounts_breakdown ? new Set(a.accounts_breakdown.map((x) => x.account_id)).size : 1 }),
      how: t('fig.cashHow'),
      formula: t('fig.cashFormula'),
    },
    {
      label: t('fig.burn'),
      value: a.average_daily_burn,
      note: t('fig.burnNote', { n: a.period_days }),
      how: t('fig.burnHow'),
      formula: t('fig.burnFormula', { n: a.period_days }),
    },
    {
      label: t('fig.in'),
      value: a.operational_inflows ?? '0',
      note: t('fig.ownNote'),
      how: t('fig.inHow', { from: formatDate(a.start_date!), to: formatDate(a.end_date!) }),
      formula: t('fig.inFormula', { amount: transfers }),
    },
    {
      label: t('fig.out'),
      value: a.operational_outflows ?? '0',
      note: t('fig.ownNote'),
      how: t('fig.outHow'),
      formula: t('fig.outFormula', { amount: transfers }),
    },
  ];

  return (
    <dl className="grid grid-cols-2 gap-y-6 lg:grid-cols-4 lg:divide-x">
      {figures.map((f) => (
        <div key={f.label} className="lg:px-6 lg:first:pl-0">
          <dt className="flex items-center gap-1 text-sm text-muted-foreground">
            {f.label}
            <Popover>
              <PopoverTrigger className="relative rounded p-0.5 text-muted-foreground after:absolute after:-inset-3 after:content-[''] hover:bg-muted hover:text-foreground" aria-label={t('fig.howAria', { label: f.label })}>
                <Info className="size-3.5" aria-hidden />
              </PopoverTrigger>
              <PopoverContent className="w-80 text-sm" align="start">
                <p className="font-medium">{t('fig.howTitle')}</p>
                <p className="mt-1 text-muted-foreground">{f.how}</p>
                <pre className="mt-3 whitespace-pre-wrap rounded bg-muted px-2.5 py-2 font-mono text-xs">{f.formula}</pre>
              </PopoverContent>
            </Popover>
          </dt>
          <dd className="mt-1 text-xl font-semibold tracking-tight">
            <Money value={f.value} />
          </dd>
          <dd className="text-xs text-muted-foreground">{f.note}</dd>
        </div>
      ))}
    </dl>
  );
}
