'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { FileText, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Money, PageHeader, SectionTitle } from '@/components/common/bits';
import { ErrorState, LoadingBlock } from '@/components/common/states';
import { RunReceipt } from '@/components/copilot/run-receipt';
import { ThinkingIndicator } from '@/components/copilot/thinking-block';
import { formatDate, formatMoney } from '@/lib/format';
import { useT, type Key } from '@/lib/i18n';
import { ApiError, api } from '@/lib/api';
import { QuickCashDialog } from '@/components/overview/quick-cash-dialog';
import { ANALYSIS, FILES, SPENDING, buildRuns } from '@/lib/mock/demo';
import { fade, spring } from '@/lib/motion';
import { useData } from '@/lib/use-data';
import { useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';
import type { CashAnalysis, RunStep } from '@/lib/types';

const shiftDay = (iso: string, n: number) => new Date(Date.parse(iso) + n * 86_400_000).toISOString().slice(0, 10);

type FileSpan = { file_name: string; account_id: string; start: string; end: string };
type Range = { start: number; days: number };

/** Files per account and the date range the timeline bars are drawn against. */
function layout(analysis: CashAnalysis, sample: boolean): { files: FileSpan[]; range: Range } {
  const files = sample
    ? FILES
    : (analysis.accounts_breakdown ?? []).map((a) => ({ file_name: a.file_name, account_id: a.account_id, start: a.start_date, end: a.end_date }));
  const starts = files.map((f) => Date.parse(f.start));
  const ends = files.map((f) => Date.parse(f.end));
  const start = Math.min(...starts);
  return { files, range: { start, days: Math.max(1, Math.round((Math.max(...ends) - start) / 86_400_000) + 1) } };
}

/** "SVB_Operating_2026-09.csv" -> "SVB Operating": a starting name the owner can edit. */
const guessName = (file: string) => file.replace(/\.[^.]+$/, '').replace(/[_-]?\d{4}([_-]?\d{2}){0,2}$/, '').replace(/[_-]+/g, ' ').trim() || file;

function Dropzone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const { t } = useT();

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const files = Array.from(e.dataTransfer.files).filter((f) => /\.(csv|pdf)$/i.test(f.name));
        if (files.length) onFiles(files);
      }}
      className={cn('rounded-xl border border-dashed bg-card px-6 py-10 text-center transition-colors', over && 'border-primary bg-accent')}
    >
      <Upload className="mx-auto size-6 text-muted-foreground" aria-hidden />
      {/* Touch screens cannot drag files, so they get the upload wording. */}
      <p className="mt-3 text-base font-medium [@media(pointer:coarse)]:hidden">{t('st.drop')}</p>
      <p className="mt-3 hidden text-base font-medium [@media(pointer:coarse)]:block">{t('st.dropTouch')}</p>
      <p className="mt-1 text-sm text-muted-foreground">{t('st.dropNote')}</p>
      <Button variant="outline" className="mt-5" onClick={() => input.current?.click()}>
        {t('st.choose')}
      </Button>
      <input
        ref={input}
        type="file"
        accept=".csv,.pdf"
        multiple
        className="sr-only"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length) onFiles(files);
          e.target.value = '';
        }}
      />
    </div>
  );
}

function FileChips({ names }: { names: string[] }) {
  const { t } = useT();
  return (
    <>
      <p className="text-sm font-medium">{t('st.received', { n: names.length })}</p>
      <ul className="mt-2 flex flex-wrap gap-2">
        {names.map((n) => (
          <li key={n} className="flex items-center gap-1.5 rounded-md bg-muted px-2 py-1 text-xs">
            <FileText className="size-3.5" aria-hidden />
            {n}
          </li>
        ))}
      </ul>
    </>
  );
}

/** Replays the sample company's run; used by "Use the sample company". */
function SampleAnalyzing({ onDone }: { onDone: () => void }) {
  const { accountNames } = useWorkspace();
  const { t } = useT();
  const steps = buildRuns(accountNames, t)[0].steps;
  const [live, setLive] = useState(1);

  useEffect(() => {
    if (live >= steps.length) return;
    const t = window.setTimeout(() => setLive((n) => n + 1), 520);
    return () => window.clearTimeout(t);
  }, [live, steps.length]);

  return (
    <motion.section initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={spring.smooth} className="rounded-xl border bg-card p-6">
      <FileChips names={FILES.map((f) => f.file_name)} />
      <div className="mt-4">
        <RunReceipt steps={steps} live={live} defaultOpen />
      </div>
      {live >= steps.length && (
        <Button className="mt-4" onClick={onDone}>
          {t('st.seeResults')}
        </Button>
      )}
    </motion.section>
  );
}

/** Sends the owner's files to the backend; each step completes when its call returns. */
function LiveAnalyzing({ files, onDone, onCancel }: { files: File[]; onDone: () => void; onCancel: () => void }) {
  const { alertThresholdDays, accountNames, update, setLive } = useWorkspace();
  const { t } = useT();
  const [steps, setSteps] = useState<RunStep[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // A step joins the receipt once its call returns; until then only its label shows as in progress.
    const start = (s: RunStep) => !cancelled && setCurrent(s.label);
    const step = (s: RunStep) => {
      if (cancelled) return;
      setSteps((list) => [...list, s]);
      setCurrent(null);
    };
    (async () => {
      setSteps([]);
      setCurrent(null);
      setError(null);
      setDone(false);
      let t0 = performance.now();
      const reading: RunStep = { label: t('lv.read'), detail: '', agent: 'liquidity', tech: 'POST /api/v1/analyze', duration_ms: 0 };
      start(reading);
      const { normalized_csv, ...analysis } = await api.analyze(files, alertThresholdDays);
      step({
        ...reading,
        detail: t('lv.readDone', { n: analysis.accepted_count, rejected: analysis.rejected_rows.length, accounts: new Set((analysis.accounts_breakdown ?? []).map((a) => a.account_id)).size || 1 }),
        duration_ms: Math.round(performance.now() - t0),
      });

      // /underwrite reads one statement; PDFs arrive back from /analyze already converted to CSV.
      // shortcut: with several CSV files only the first is scored; send a combined CSV once /underwrite accepts many files.
      const csvFile = files.find((f) => /\.csv$/i.test(f.name));
      const source = normalized_csv ? new Blob([normalized_csv], { type: 'text/csv' }) : csvFile;
      let underwrite;
      if (source) {
        t0 = performance.now();
        const scoring: RunStep = { label: t('lv.score'), detail: '', agent: 'credit', tech: 'POST /api/v1/underwrite · underwrite_sme_transactions', duration_ms: 0 };
        start(scoring);
        const res = await api.underwrite(source, csvFile?.name ?? 'statements.csv');
        underwrite = { dossier: res.dossier, options: res.matched_options };
        step({ ...scoring, detail: t('lv.scoreDone', { score: res.dossier.liquidity_score ?? '–', n: res.matched_options.length }), duration_ms: Math.round(performance.now() - t0) });
      }
      if (cancelled) return;

      const names = { ...accountNames };
      for (const a of analysis.accounts_breakdown ?? []) names[a.account_id] ??= guessName(a.file_name);
      setLive({ analysis, underwrite, receivables: undefined, intents: [] });
      update({ hasData: true, source: 'live', ...(analysis.currency ? { homeCurrency: analysis.currency } : {}), accountNames: names, intentStatus: {}, intentDecidedAt: {} });
      setDone(true);
    })().catch((e: unknown) => {
      if (cancelled) return;
      setCurrent(null);
      setError(e instanceof ApiError ? e.message : t('common.timeout'));
    });
    return () => {
      cancelled = true;
    };
    // One run per attempt; the settings it reads are fixed while it runs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files, attempt]);

  return (
    <motion.section initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={spring.smooth} className="rounded-xl border bg-card p-6">
      <FileChips names={files.map((f) => f.name)} />
      {steps.length > 0 && (
        <div className="mt-4">
          <RunReceipt steps={steps} holdOpen={!done} defaultOpen />
        </div>
      )}
      {current && !error && (
        <div className="mt-3">
          <ThinkingIndicator label={current} />
        </div>
      )}
      {error && (
        <div className="mt-4 rounded-md border border-critical/40 bg-critical/5 px-4 py-3 text-sm" role="alert">
          <p className="font-medium text-critical-text">{t('lv.failed')}</p>
          <p className="mt-1 text-ink-2">{error}</p>
          <div className="mt-3 flex gap-2">
            <Button size="sm" onClick={() => setAttempt((n) => n + 1)}>
              {t('common.retry')}
            </Button>
            <Button size="sm" variant="outline" onClick={onCancel}>
              {t('lv.back')}
            </Button>
          </div>
        </div>
      )}
      {done && (
        <Button className="mt-4" onClick={onDone}>
          {t('st.seeResults')}
        </Button>
      )}
    </motion.section>
  );
}

function AccountRow({ id, files: allFiles, range, analysis }: { id: string; files: FileSpan[]; range: Range; analysis: CashAnalysis }) {
  const { accountNames, renameAccount } = useWorkspace();
  const { t } = useT();
  const files = allFiles.filter((f) => f.account_id === id);
  const summaries = (analysis.accounts_breakdown ?? []).filter((a) => a.account_id === id);
  const latest = summaries[summaries.length - 1];
  const pct = (iso: string) => ((Date.parse(iso) - range.start) / 86_400_000 / range.days) * 100;
  const gaps = files.slice(1).flatMap((f, i) => {
    const from = shiftDay(files[i].end, 1);
    const to = shiftDay(f.start, -1);
    if (from > to) return [];
    return [from === to ? formatDate(from) : t('common.range', { from: formatDate(from), to: formatDate(to) })];
  });
  const txCount = summaries.reduce((s, a) => s + a.transaction_count, 0);
  const [name, setName] = useState(accountNames[id] ?? id);

  return (
    <li className="grid gap-4 py-5 md:grid-cols-[minmax(200px,260px)_1fr_auto] md:items-center">
      <div>
        <label htmlFor={`name-${id}`} className="sr-only">
          {t('st.accountName')}
        </label>
        <Input
          id={`name-${id}`}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => renameAccount(id, name)}
          className="h-8 border-transparent px-2 -ml-2 text-base font-medium sm:text-sm shadow-none hover:border-input focus-visible:border-input"
        />
        <p className="text-xs text-muted-foreground">
          {t('count.files', { n: files.length })}, {t('count.tx', { n: txCount })}, {analysis.currency}
        </p>
      </div>

      <div>
        <div className="relative h-6 rounded bg-muted" aria-hidden>
          {files.map((f) => (
            <div
              key={f.file_name}
              className="absolute inset-y-1 rounded-sm bg-primary/70"
              style={{ left: `${pct(f.start)}%`, width: `calc(${pct(f.end) - pct(f.start) + 100 / range.days}% - 2px)` }}
              title={`${f.file_name}: ${formatDate(f.start)} to ${formatDate(f.end)}`}
            />
          ))}
        </div>
        <p className="mt-1.5 text-xs text-muted-foreground">
          {files.map((f) => t('common.range', { from: formatDate(f.start), to: formatDate(f.end) })).join(', ')}.{' '}
          {gaps.length > 0 ? (
            <span className="text-warning-text">{t('st.gap', { ranges: gaps.join(t('st.and')) })}</span>
          ) : (
            <span>{t('st.connected')}</span>
          )}
        </p>
      </div>

      <div className="md:text-right">
        <p className="text-xs text-muted-foreground">{t('st.closing')}</p>
        {latest && <Money value={latest.closing_balance} className="text-base font-semibold" />}
      </div>
    </li>
  );
}

function Results({ analysis, sample }: { analysis: CashAnalysis; sample: boolean }) {
  const { clearData, accountNames } = useWorkspace();
  const { t } = useT();
  const maxSpend = Math.max(...SPENDING.map((s) => s.cents));
  const { files, range } = layout(analysis, sample);
  const accounts = Array.from(new Set(files.map((f) => f.account_id)));
  const transfers = analysis.internal_transfers ?? [];

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={fade} className="space-y-12">
      <section>
        <SectionTitle aside={t('st.renameHint')}>{t('st.accounts')}</SectionTitle>
        <ul className="divide-y border-y">
          {accounts.map((id) => (
            <AccountRow key={id} id={id} files={files} range={range} analysis={analysis} />
          ))}
        </ul>
      </section>

      <div className="grid gap-12 lg:grid-cols-2">
        {transfers.length > 0 && (
          <section>
            <SectionTitle aside={formatMoney(analysis.internal_transfers_excluded ?? '0')}>{t('st.transfers')}</SectionTitle>
            <p className="mb-3 text-sm text-muted-foreground">{t('st.transfersNote')}</p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('col.date')}</TableHead>
                  <TableHead>{t('col.from')}</TableHead>
                  <TableHead>{t('col.to')}</TableHead>
                  <TableHead className="text-right">{t('col.amount')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {transfers.map((x) => (
                  <TableRow key={x.outflow_tx_id}>
                    <TableCell className="figures">{formatDate(x.transfer_date)}</TableCell>
                    <TableCell>{accountNames[x.outflow_account] ?? x.outflow_account}</TableCell>
                    <TableCell>{accountNames[x.inflow_account] ?? x.inflow_account}</TableCell>
                    <TableCell className="text-right">
                      <Money value={x.amount} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </section>
        )}

        <section>
          <SectionTitle aside={t('count.rows', { n: analysis.rejected_rows.length })}>{t('st.rejected')}</SectionTitle>
          <p className="mb-3 text-sm text-muted-foreground">{t('st.rejectedNote')}</p>
          {analysis.rejected_rows.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('col.row')}</TableHead>
                  <TableHead>{t('col.reason')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {analysis.rejected_rows.map((r) => (
                  <TableRow key={r.row_number}>
                    <TableCell className="figures">{r.row_number}</TableCell>
                    <TableCell>{t(`reason.${r.reason_code}` as Key)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </section>
      </div>

      {/* Spending by category comes only with the sample company until the backend returns categories. */}
      {sample && (
        <section>
          <SectionTitle aside={t('common.range', { from: formatDate(analysis.start_date!), to: formatDate(analysis.end_date!) })}>{t('st.spend')}</SectionTitle>
          <p className="mb-4 max-w-2xl text-sm text-muted-foreground">{t('st.spendNote')}</p>
          <ul className="space-y-3">
            {SPENDING.map((s) => (
              <li key={s.category} className="grid grid-cols-[140px_1fr_110px] items-center gap-4 text-sm">
                <span>{t(`cat.${s.category}` as Key)}</span>
                <span className="h-2 rounded-full bg-muted">
                  <motion.span
                    className="block h-2 origin-left rounded-full bg-series-1"
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: s.cents / maxSpend }}
                    transition={spring.gentle}
                  />
                </span>
                <Money value={s.amount} className="text-right" />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="border-t pt-8">
        <Dialog>
          <DialogTrigger asChild>
            <Button variant="outline">{t('st.remove')}</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('st.removeTitle')}</DialogTitle>
              <DialogDescription>{t('st.removeBody')}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline">{t('st.keep')}</Button>
              </DialogClose>
              <DialogClose asChild>
                <Button variant="destructive" onClick={clearData}>
                  {t('st.remove')}
                </Button>
              </DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </section>
    </motion.div>
  );
}

type Incoming = { kind: 'sample' } | { kind: 'live'; files: File[] };

export default function StatementsPage() {
  const state = useData(
    () => ANALYSIS,
    (live) => live.analysis,
  );
  const { loadSample, source } = useWorkspace();
  const { t } = useT();
  const [incoming, setIncoming] = useState<Incoming | null>(null);

  return (
    <div>
      <PageHeader title={t('nav.statements')} description={t('st.desc')} actions={<QuickCashDialog />} />
      <div className="space-y-12">
        <AnimatePresence mode="wait" initial={false}>
          {incoming?.kind === 'live' ? (
            <LiveAnalyzing key="live" files={incoming.files} onDone={() => setIncoming(null)} onCancel={() => setIncoming(null)} />
          ) : incoming?.kind === 'sample' ? (
            <SampleAnalyzing
              key="sample"
              onDone={() => {
                loadSample();
                setIncoming(null);
              }}
            />
          ) : (
            <motion.div key="drop" exit={{ opacity: 0 }} transition={fade}>
              <Dropzone onFiles={(files) => setIncoming({ kind: 'live', files })} />
              {/* Direct entry or sample company */}
              <div className="mt-3 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-center text-sm text-muted-foreground">
                <QuickCashDialog
                  defaultMode="SET_BALANCE"
                  trigger={
                    <button type="button" className="py-2 font-medium text-foreground underline underline-offset-2">
                      {t('quickCash.triggerDirect')}
                    </button>
                  }
                />
                {(state.status === 'empty' || source === 'live') && (
                  <span>
                    <span aria-hidden className="mr-3">•</span>
                    {t(state.status === 'empty' ? 'st.noFiles' : 'lv.showingYours')}{' '}
                    <button type="button" onClick={() => setIncoming({ kind: 'sample' })} className="py-2 font-medium text-foreground underline underline-offset-2">
                      {t('st.useSample')}
                    </button>
                  </span>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {!incoming && state.status === 'loading' && <LoadingBlock rows={4} />}
        {!incoming && state.status === 'error' && <ErrorState message={state.message} retry={state.retry} />}
        {!incoming && state.status === 'ready' && <Results analysis={state.data} sample={source === 'sample'} />}
      </div>
    </div>
  );
}
