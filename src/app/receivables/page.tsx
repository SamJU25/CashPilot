'use client';

import { useRef, useState } from 'react';
import { motion } from 'motion/react';
import { Fingerprint, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Money, PageHeader, SectionTitle } from '@/components/common/bits';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/common/states';
import { formatDate, formatMoney } from '@/lib/format';
import { ApiError, api } from '@/lib/api';
import { RECEIVABLES } from '@/lib/mock/demo';
import { spring } from '@/lib/motion';
import { cn } from '@/lib/utils';
import { useData } from '@/lib/use-data';
import { useWorkspace } from '@/lib/workspace';
import type { Debtor } from '@/lib/types';
import { useT, type Key } from '@/lib/i18n';
import { ReminderDialog } from '@/components/receivables/reminder-dialog';
import { BlockchainVerifyDialog } from '@/components/receivables/blockchain-verify-dialog';

// Lateness escalates from caution to critical; "not yet due" stays neutral.
const BUCKET_COLORS: Record<string, string> = {
  current: 'rgb(var(--muted-foreground) / 0.35)',
  d1_30: 'rgb(var(--warning) / 0.7)',
  d31_60: 'rgb(var(--serious))',
  d61_90: 'rgb(var(--critical))',
  d90_plus: 'rgb(var(--critical-text))',
};

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
  const [verifying, setVerifying] = useState<Debtor | null>(null);
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
  const buckets = Object.entries(r.buckets);
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

      <section className="mt-10 rounded-xl border bg-card p-5 sm:p-6">
        <SectionTitle aside={t('rec.asOf', { date: formatDate(r.as_of_date, true) })}>{t('rec.howLate')}</SectionTitle>
        <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full" role="img" aria-label={t('rec.barAria')}>
          {buckets
            .filter(([, b]) => Number(b.percentage) > 0)
            .map(([key, b], i) => (
              <Tooltip key={key}>
                <TooltipTrigger asChild>
                  <motion.span
                    className="h-full origin-left first:rounded-l-full last:rounded-r-full"
                    style={{ width: `${b.percentage}%`, background: BUCKET_COLORS[key] }}
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ ...spring.gentle, delay: i * 0.03 }}
                  />
                </TooltipTrigger>
                <TooltipContent>
                  {t('rec.bucketTip', { label: t(`bucket.${key}` as Key), amount: formatMoney(b.amount), count: t('count.invoices', { n: b.invoice_count }) })}
                </TooltipContent>
              </Tooltip>
            ))}
        </div>
        <ul className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-5">
          {buckets.map(([key, b]) => (
            <li key={key}>
              <span className="flex items-center gap-2 text-muted-foreground">
                <span className="size-2 rounded-full" style={{ background: BUCKET_COLORS[key] }} aria-hidden />
                {t(`bucket.${key}` as Key)}
              </span>
              <Money value={b.amount} className="mt-0.5 block font-medium" />
            </li>
          ))}
        </ul>
      </section>

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
                <div className="flex gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setVerifying(d)}
                    className="flex-1 justify-center gap-1.5 text-xs text-muted-foreground border hover:text-foreground"
                  >
                    <Fingerprint className="size-3.5" aria-hidden />
                    {t('rec.blockchainAudit')}
                  </Button>
                  {late && (
                    <Button variant="outline" size="sm" className="flex-1" onClick={() => setDrafting(d)}>
                      {t('rec.draft')}
                    </Button>
                  )}
                </div>
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
                <TableHead>{t('rec.blockchainAudit')}</TableHead>
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
                  <TableCell className="figures text-right">{pct(d.share_of_total_ar)}%</TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setVerifying(d)}
                      className="h-8 gap-1.5 px-2 text-xs font-normal text-muted-foreground hover:text-foreground"
                    >
                      <Fingerprint className="size-3.5" aria-hidden />
                      {t('rec.verifiedBadge')}
                    </Button>
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
      <BlockchainVerifyDialog debtor={verifying} onClose={() => setVerifying(null)} />
    </div>
  );
}
