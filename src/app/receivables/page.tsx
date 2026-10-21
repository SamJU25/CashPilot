'use client';

import { useRef, useState } from 'react';
import { motion } from 'motion/react';
import { Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Money, PageHeader, SectionTitle } from '@/components/common/bits';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/common/states';
import { centsToString, formatDate, formatMoney, stringToCents } from '@/lib/format';
import { Donut, Legend, type Segment } from '@/components/charts/kit';
import { BUCKET_COLORS } from '@/components/charts/colors';
import { ApiError, api } from '@/lib/api';
import { RECEIVABLES } from '@/lib/mock/demo';
import { spring } from '@/lib/motion';
import { cn } from '@/lib/utils';
import { useData } from '@/lib/use-data';
import { useWorkspace } from '@/lib/workspace';
import type { Debtor } from '@/lib/types';
import { useT, type Key } from '@/lib/i18n';
import { ReminderDialog } from '@/components/receivables/reminder-dialog';

const pct = (v: string) => Math.round(Number(v));

/** Sends an invoice export to /analyze/invoices; the ageing report replaces any earlier one. */
function InvoiceUpload({
  variant = 'default',
  centered = false,
}: {
  variant?: 'default' | 'outline';
  centered?: boolean;
}) {
  const { t } = useT();
  const { update, setLive, source, hasData } = useWorkspace();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const receivables = await api.invoices(file);
      // Invoices on their own switch the workspace to the owner's files; the sample company's statements leave with it.
      if (source === 'sample') setLive({ analysis: undefined, underwrite: undefined, intents: [], receivables });
      else setLive({ receivables });
      if (source === 'sample' || !hasData) update({ hasData: true, source: 'live', ...(receivables.currency ? { homeCurrency: receivables.currency } : {}), intentStatus: {}, intentDecidedAt: {} });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('common.timeout'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={cn('flex flex-col', centered && 'items-center text-center')}>
      <Button variant={variant} onClick={() => input.current?.click()} disabled={busy}>
        <Upload aria-hidden />
        {busy ? t('lv.uploading') : t('lv.invoices')}
      </Button>
      <input
        ref={input}
        type="file"
        accept=".csv"
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) send(file);
          e.target.value = '';
        }}
      />
      <a href="/samples/invoices_example.csv" download className="mt-2 block text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground">
        {t('lv.invoiceExample')}
      </a>
      {error && (
        <p className="mt-2 text-sm text-critical-text" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export default function ReceivablesPage() {
  const state = useData(
    () => RECEIVABLES,
    (live) => live.receivables,
  );
  const [drafting, setDrafting] = useState<Debtor | null>(null);
  const { source } = useWorkspace();
  const { t } = useT();
  const sample = source === 'sample';

  const header = <PageHeader title={t('nav.receivables')} description={t('rec.desc')} />;

  if (state.status === 'loading') return <>{header}<LoadingBlock rows={5} /></>;
  if (state.status === 'error') return <>{header}<ErrorState message={state.message} retry={state.retry} /></>;
  if (state.status === 'empty')
    return (
      <>
        {header}
        <EmptyState title={t('rec.emptyTitle')} body={t('rec.emptyBody')} action={null}>
          <InvoiceUpload centered />
        </EmptyState>
      </>
    );

  const r = state.data;
  const bucketSegments: Segment[] = Object.entries(r.buckets).map(([key, b]) => ({ key, label: t(`bucket.${key}` as Key), value: stringToCents(b.amount), color: BUCKET_COLORS[key] }));
  const byOverdue = r.top_debtors.filter((d) => stringToCents(d.overdue_amount) > 0).sort((a, b) => stringToCents(b.overdue_amount) - stringToCents(a.overdue_amount));
  const topOverdue = Math.max(1, ...byOverdue.map((d) => stringToCents(d.overdue_amount)));
  const top = r.top_debtors[0];

  return (
    <div>
      {header}
      <div className="flex flex-wrap items-start justify-between gap-4">
        {/* The backend's advisory is English only; the sample company's is translated. */}
        <p className="max-w-2xl text-lg text-ink-2">{sample ? t('rec.advisory') : r.summary_advisory}</p>
        {!sample && <InvoiceUpload variant="outline" />}
      </div>

      <dl className="mt-8 grid grid-cols-2 gap-y-6 rounded-xl border bg-card px-5 py-5 sm:px-6 lg:grid-cols-4 lg:divide-x">
        {[
          { label: t('rec.owed'), value: <Money value={r.total_ar} /> },
          { label: t('rec.overdue'), value: <Money value={r.total_overdue} />, note: t('rec.overdueNote', { pct: pct(r.overdue_ratio_pct) }) },
          { label: t('rec.avgLate'), value: <span className="figures">{r.weighted_average_days_overdue}</span>, note: t('rec.weighted') },
          { label: t('rec.largest'), value: <span className="figures">{pct(r.top_1_concentration_pct)}%</span>, note: top?.customer_name },
        ].map((f) => (
          <div key={f.label} className="lg:px-6 lg:first:pl-0">
            <dt className="text-sm text-muted-foreground">{f.label}</dt>
            <dd className="mt-1 font-display text-2xl font-semibold tracking-tight">{f.value}</dd>
            {f.note && <dd className="text-xs text-muted-foreground">{f.note}</dd>}
          </div>
        ))}
      </dl>

      <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <section className="rounded-xl border bg-card p-5 sm:p-6">
          <SectionTitle aside={t('rec.asOf', { date: formatDate(r.as_of_date, true) })}>{t('rec.howLate')}</SectionTitle>
          <div className="flex flex-col items-center gap-6 sm:flex-row">
            <Donut segments={bucketSegments} label={t('rec.barAria')}>
              <span className="text-xs text-muted-foreground">{t('rec.overdue')}</span>
              <Money value={r.total_overdue} cents={false} className="font-display text-2xl font-semibold" />
              <span className="text-xs text-muted-foreground">{t('rec.overdueNote', { pct: pct(r.overdue_ratio_pct) })}</span>
            </Donut>
            <Legend segments={bucketSegments} format={(v) => formatMoney(centsToString(v), undefined, { cents: false })} />
          </div>
        </section>
        <section className="rounded-xl border bg-card p-5 sm:p-6">
          <SectionTitle aside={t('rec.byCustomerAside')}>{t('rec.byCustomer')}</SectionTitle>
          <ul className="space-y-3">
            {byOverdue.map((d, i) => (
              <li key={d.customer_name} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 text-sm">
                <span className="truncate">{d.customer_name}</span>
                <span className="relative h-2.5 rounded-full bg-muted" title={t('rec.lateTip', { n: d.max_days_overdue })}>
                  <motion.span
                    className={cn('absolute inset-y-0 left-0 rounded-full', d.max_days_overdue > 60 ? 'bg-critical' : d.max_days_overdue > 30 ? 'bg-serious' : 'bg-warning/70')}
                    style={{ width: `${(stringToCents(d.overdue_amount) / topOverdue) * 100}%`, originX: 0 }}
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ ...spring.gentle, delay: i * 0.03 }}
                  />
                </span>
                <span className="flex items-baseline gap-2">
                  <Money value={d.overdue_amount} cents={false} className="font-medium" />
                  <span className="figures w-12 text-right text-xs text-muted-foreground">{t('rec.daysLate', { n: d.max_days_overdue })}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="mt-6 rounded-xl border bg-card p-5 sm:p-6">
        <SectionTitle>{t('rec.customers')}</SectionTitle>
        {/* Phones get one card per customer, so the reminder button never sits off-screen in a wide table. */}
        <ul className="divide-y rounded-lg border md:hidden">
          {r.top_debtors.map((d) => {
            const late = Number(d.overdue_amount) > 0;
            return (
              <li key={d.customer_name} className="space-y-3 p-4">
                <div className="flex items-baseline justify-between gap-3">
                  <p className="font-medium">{d.customer_name}</p>
                  <p className="figures shrink-0 text-xs text-muted-foreground">{t('col.share')} {pct(d.share_of_total_ar)}%</p>
                </div>
                <dl className="grid grid-cols-3 gap-2 text-sm">
                  <div>
                    <dt className="text-xs text-muted-foreground">{t('col.owed')}</dt>
                    <dd><Money value={d.total_open_balance} /></dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">{t('col.overdue')}</dt>
                    <dd>{late ? <Money value={d.overdue_amount} /> : <span className="text-muted-foreground">{t('rec.none')}</span>}</dd>
                  </div>
                  <div className="text-right">
                    <dt className="text-xs text-muted-foreground">{t('col.mostLate')}</dt>
                    <dd className={`figures ${d.max_days_overdue > 45 ? 'text-critical-text' : ''}`}>{d.max_days_overdue || '–'}</dd>
                  </div>
                </dl>
                {late && (
                  <Button variant="outline" size="sm" className="w-full" onClick={() => setDrafting(d)}>
                    {t('rec.draft')}
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
        <div className="hidden overflow-x-auto md:block">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('col.customer')}</TableHead>
                <TableHead className="text-right">{t('col.owed')}</TableHead>
                <TableHead className="text-right">{t('col.overdue')}</TableHead>
                <TableHead className="text-right">{t('col.mostLate')}</TableHead>
                <TableHead className="text-right">{t('col.share')}</TableHead>
                <TableHead className="w-0" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {r.top_debtors.map((d) => (
                <TableRow key={d.customer_name}>
                  <TableCell className="font-medium">{d.customer_name}</TableCell>
                  <TableCell className="text-right">
                    <Money value={d.total_open_balance} />
                  </TableCell>
                  <TableCell className="text-right">
                    {Number(d.overdue_amount) > 0 ? <Money value={d.overdue_amount} /> : <span className="text-muted-foreground">{t('rec.none')}</span>}
                  </TableCell>
                  <TableCell className={`figures text-right ${d.max_days_overdue > 45 ? 'text-critical-text' : ''}`}>{d.max_days_overdue || '–'}</TableCell>
                  <TableCell className="text-right">
                    <span className="inline-flex items-center gap-2.5">
                      <span className="relative hidden h-1.5 w-16 rounded-full bg-muted xl:block" aria-hidden>
                        <span className="absolute inset-y-0 left-0 rounded-full bg-ink-2/70" style={{ width: `${Math.min(100, Number(d.share_of_total_ar))}%` }} />
                      </span>
                      <span className="figures w-9">{pct(d.share_of_total_ar)}%</span>
                    </span>
                  </TableCell>
                  <TableCell>
                    {Number(d.overdue_amount) > 0 && (
                      <Button variant="outline" size="sm" onClick={() => setDrafting(d)}>
                        {t('rec.draft')}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="mt-10">
        <SectionTitle>{t('rec.next')}</SectionTitle>
        <ol className="max-w-2xl list-decimal space-y-2 pl-5 text-sm text-ink-2 marker:text-muted-foreground">
          {sample ? (
            <>
              <li>{t('rec.action1', { amount: formatMoney(top.overdue_amount), from: formatDate('2026-10-28'), to: formatDate('2026-11-01') })}</li>
              <li>{t('rec.action2')}</li>
              <li>{t('rec.action3')}</li>
            </>
          ) : (
            r.recommended_actions.map((a) => <li key={a}>{a}</li>)
          )}
        </ol>
      </section>

      <ReminderDialog debtor={drafting} onClose={() => setDrafting(null)} />
    </div>
  );
}
