"use client";

import { useEffect, useRef, useState } from "react";
import { Donut, MiniArea } from "@/components/charts/kit";
import { CATEGORY_COLORS } from "@/components/charts/colors";

import { AnimatePresence, motion } from "motion/react";

import {
  AlertCircle,
  ArrowRight,
  Ban,
  CalendarX2,
  Check,
  CheckCheck,
  CheckCircle2,
  CopyX,
  FileText,
  Pencil,
  Coins,
  ShieldCheck,
  Upload,
} from "lucide-react";

import { Button } from "@/components/ui/button";

import { Input } from "@/components/ui/input";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { Money, PageHeader, SectionTitle } from "@/components/common/bits";

import { ErrorState, LoadingBlock } from "@/components/common/states";

import { RunReceipt } from "@/components/copilot/run-receipt";

import { ThinkingIndicator } from "@/components/copilot/thinking-block";

import { centsToString, formatDate, formatMoney, stringToCents } from "@/lib/format";

import { useT, type Key } from "@/lib/i18n";

import { ApiError, api } from "@/lib/api";

import { QuickCashDialog } from "@/components/overview/quick-cash-dialog";
import { EntriesLedger } from "@/components/overview/entries-ledger";

import { ANALYSIS, FILES, SERIES, SPENDING, buildRuns } from "@/lib/mock/demo";

import { fade, spring } from "@/lib/motion";

import { useData } from "@/lib/use-data";

import { useWorkspace } from "@/lib/workspace";

import { cn } from "@/lib/utils";

import type { CashAnalysis, RejectedRow, RunStep } from "@/lib/types";

const shiftDay = (iso: string | null | undefined, n: number) => {
  if (!iso) return "";
  const parsed = Date.parse(String(iso));
  if (isNaN(parsed)) return "";
  return new Date(parsed + n * 86_400_000).toISOString().slice(0, 10);
};

type FileSpan = {
  file_name: string;
  account_id: string;
  start: string;
  end: string;
};
type Range = { start: number; days: number };

/** Files per account and the date range the timeline bars are drawn against. */
function layout(
  analysis: CashAnalysis,
  sample: boolean,
): { files: FileSpan[]; range: Range } {
  const files = sample
    ? FILES
    : (analysis?.accounts_breakdown ?? []).map((a) => ({
        file_name: a.file_name,
        account_id: a.account_id,
        start: a.start_date,
        end: a.end_date,
      }));
  const starts = files.map((f) => Date.parse(f.start)).filter((n) => !isNaN(n));
  const ends = files.map((f) => Date.parse(f.end)).filter((n) => !isNaN(n));
  const start = starts.length > 0 ? Math.min(...starts) : Date.now();
  const end = ends.length > 0 ? Math.max(...ends) : start;
  return {
    files,
    range: {
      start,
      days: Math.max(1, Math.round((end - start) / 86_400_000) + 1),
    },
  };
}

/** "SVB_Operating_2026-09.csv" -> "SVB Operating": a starting name the owner can edit. */

const guessName = (file: string) =>
  file
    .replace(/\.[^.]+$/, "")
    .replace(/[_-]?\d{4}([_-]?\d{2}){0,2}$/, "")
    .replace(/[_-]+/g, " ")
    .trim() || file;

function Dropzone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);

  const [over, setOver] = useState(false);

  const { t } = useT();

  return (
    <div
      onClick={() => input.current?.click()}

      onDragOver={(e) => {
        e.preventDefault();

        setOver(true);
      }}

      onDragLeave={() => setOver(false)}

      onDrop={(e) => {
        e.preventDefault();

        setOver(false);

        const files = Array.from(e.dataTransfer.files).filter((f) =>
          /\.(csv|pdf)$/i.test(f.name),
        );

        if (files.length) onFiles(files);
      }}

      className={cn(
        "cursor-pointer rounded-xl border border-dashed bg-card px-6 py-10 text-center transition-colors hover:border-primary/60 hover:bg-accent/40",

        over && "border-primary bg-accent",
      )}
    >
      <Upload className="mx-auto size-6 text-muted-foreground" aria-hidden />

      {/* Touch screens cannot drag files, so they get the upload wording. */}

      <p className="mt-3 text-base font-medium [@media(pointer:coarse)]:hidden">
        {t("st.drop")}
      </p>

      <p className="mt-3 hidden text-base font-medium [@media(pointer:coarse)]:block">
        {t("st.dropTouch")}
      </p>

      <p className="mt-1 text-sm text-muted-foreground">{t("st.dropNote")}</p>

      <Button
        variant="outline"

        className="mt-5 pointer-events-auto"

        onClick={(e) => {
          e.stopPropagation();

          input.current?.click();
        }}
      >
        {t("st.choose")}
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

          e.target.value = "";
        }}
      />
    </div>
  );
}

function CompactDropzone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);

  const [over, setOver] = useState(false);

  const { t } = useT();

  return (
    <div
      onClick={() => input.current?.click()}

      onDragOver={(e) => {
        e.preventDefault();

        setOver(true);
      }}

      onDragLeave={() => setOver(false)}

      onDrop={(e) => {
        e.preventDefault();

        setOver(false);

        const files = Array.from(e.dataTransfer.files).filter((f) =>
          /\.(csv|pdf)$/i.test(f.name),
        );

        if (files.length) onFiles(files);
      }}

      className={cn(
        "group flex cursor-pointer flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-dashed bg-card/60 px-5 py-3.5 transition-colors hover:border-primary hover:bg-accent/30",

        over && "border-primary bg-accent",
      )}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground group-hover:text-foreground">
          <Upload className="size-4" aria-hidden />
        </div>

        <div className="min-w-0 text-left">
          <p className="text-xs font-medium text-foreground">{t("st.drop")}</p>

          <p className="text-[11px] text-muted-foreground">
            {t("st.dropNote")}
          </p>
        </div>
      </div>

      <Button
        variant="outline"

        size="sm"

        className="h-8 shrink-0 text-xs"

        onClick={(e) => {
          e.stopPropagation();

          input.current?.click();
        }}
      >
        {t("st.choose")}
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

          e.target.value = "";
        }}
      />
    </div>
  );
}

function FileChips({ names }: { names: string[] }) {
  const { t } = useT();

  return (
    <>
      <p className="text-sm font-medium">
        {t("st.received", { n: names.length })}
      </p>

      <ul className="mt-2 flex flex-wrap gap-2">
        {names.map((n) => (
          <li
            key={n}
            className="flex items-center gap-1.5 rounded-md bg-muted px-2 py-1 text-xs"
          >
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
    <motion.section
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={spring.smooth}
      className="rounded-xl border bg-card p-6"
    >
      <FileChips names={FILES.map((f) => f.file_name)} />

      <div className="mt-4">
        <RunReceipt steps={steps} live={live} defaultOpen />
      </div>

      {live >= steps.length && (
        <Button className="mt-4" onClick={onDone}>
          {t("st.seeResults")}
        </Button>
      )}
    </motion.section>
  );
}

/** Sends the owner's files to the backend; each step completes when its call returns. */

function LiveAnalyzing({
  files,
  onDone,
  onCancel,
}: {
  files: File[];
  onDone: () => void;
  onCancel: () => void;
}) {
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

      const reading: RunStep = {
        label: t("lv.read"),
        detail: "",
        agent: "liquidity",
        tech: "POST /api/v1/analyze",
        duration_ms: 0,
      };

      start(reading);

      const { normalized_csv, ...analysis } = await api.analyze(
        files,
        alertThresholdDays,
      );

      step({
        ...reading,

        detail: t("lv.readDone", {
          n: analysis.accepted_count,
          rejected: (analysis?.rejected_rows ?? []).length,
          accounts:
            new Set(
              (analysis.accounts_breakdown ?? []).map((a) => a.account_id),
            ).size || 1,
        }),

        duration_ms: Math.round(performance.now() - t0),
      });

      // /underwrite reads one statement; PDFs arrive back from /analyze already converted to CSV.

      // shortcut: with several CSV files only the first is scored; send a combined CSV once /underwrite accepts many files.

      const csvFile = files.find((f) => /\.csv$/i.test(f.name));

      const source = normalized_csv
        ? new Blob([normalized_csv], { type: "text/csv" })
        : csvFile;

      let underwrite;

      if (source) {
        t0 = performance.now();

        const scoring: RunStep = {
          label: t("lv.score"),
          detail: "",
          agent: "credit",
          tech: "POST /api/v1/underwrite · underwrite_sme_transactions",
          duration_ms: 0,
        };

        start(scoring);

        const res = await api.underwrite(
          source,
          csvFile?.name ?? "statements.csv",
        );

        underwrite = { dossier: res.dossier, options: res.matched_options };

        step({
          ...scoring,
          detail: t("lv.scoreDone", {
            score: res.dossier.liquidity_score ?? "–",
            n: res.matched_options.length,
          }),
          duration_ms: Math.round(performance.now() - t0),
        });
      }

      if (cancelled) return;

      const names = { ...accountNames };

      for (const a of analysis.accounts_breakdown ?? [])
        names[a.account_id] ??= guessName(a.file_name);

      setLive({ analysis, underwrite, receivables: undefined, intents: [], entries: [] });

      update({
        hasData: true,
        source: "live",
        ...(analysis.currency ? { homeCurrency: analysis.currency } : {}),
        accountNames: names,
        intentStatus: {},
        intentDecidedAt: {},
      });

      setDone(true);
    })().catch((e: unknown) => {
      if (cancelled) return;

      setCurrent(null);

      setError(e instanceof ApiError ? e.message : t("common.timeout"));
    });

    return () => {
      cancelled = true;
    };

    // One run per attempt; the settings it reads are fixed while it runs.

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files, attempt]);

  return (
    <motion.section
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={spring.smooth}
      className="rounded-xl border bg-card p-6"
    >
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
        <div
          className="mt-4 rounded-md border border-critical/40 bg-critical/5 px-4 py-3 text-sm"
          role="alert"
        >
          <p className="font-medium text-critical-text">{t("lv.failed")}</p>

          <p className="mt-1 text-ink-2">{error}</p>

          <div className="mt-3 flex gap-2">
            <Button size="sm" onClick={() => setAttempt((n) => n + 1)}>
              {t("common.retry")}
            </Button>

            <Button size="sm" variant="outline" onClick={onCancel}>
              {t("lv.back")}
            </Button>
          </div>
        </div>
      )}

      {done && (
        <Button className="mt-4" onClick={onDone}>
          {t("st.seeResults")}
        </Button>
      )}
    </motion.section>
  );
}

function AccountRow({
  id,
  files: allFiles,
  analysis,
  history,
}: {
  id: string;
  files: FileSpan[];
  analysis: CashAnalysis;
  history: { date: string; cents: number }[];
}) {
  const { accountNames, renameAccount, live } = useWorkspace();
  const { t, lang } = useT();
  const manual = analysis.document_format === "MANUAL";
  // An account whose entries all came from bank alert emails was not typed in.
  const own = (live.entries ?? []).filter((e) => e.accountId === id);
  const fromEmail = own.length > 0 && own.every((e) => e.alertId);
  const files = [...allFiles.filter((f) => f.account_id === id)].sort((a, b) =>
    (a.start || "").localeCompare(b.start || ""),
  );
  const summaries = (analysis?.accounts_breakdown ?? []).filter(
    (a) => a.account_id === id,
  );
  const latest = summaries[summaries.length - 1];

  const missingGaps: { from: string; to: string; label: string }[] = [];
  for (let i = 0; i < files.length - 1; i++) {
    if (!files[i]?.end || !files[i + 1]?.start) continue;
    const from = shiftDay(files[i].end, 1);
    const to = shiftDay(files[i + 1].start, -1);
    if (from && to && from <= to) {
      missingGaps.push({
        from,
        to,
        label:
          from === to
            ? formatDate(from)
            : `${formatDate(from)} - ${formatDate(to)}`,
      });
    }
  }

  const gaps = missingGaps.map((g) => g.label);
  const txCount = summaries.reduce((s, a) => s + (a.transaction_count || 0), 0);
  const [name, setName] = useState(accountNames[id] ?? id);

  const accountRejected = (analysis?.rejected_rows ?? []).filter((r) => {
    if (r.account_id) return r.account_id === id;
    const d = r.suggested_fix?.posted_on;
    if (!d) return false;
    return files.some((f) => f.start && f.end && d >= f.start && d <= f.end);
  });

  const closing = latest?.closing_balance ?? analysis.current_balance;
  // First point of each month, placed on the same index scale the chart draws with.
  const months = history.flatMap((p, k) =>
    k === 0 || p.date.slice(0, 7) !== history[k - 1].date.slice(0, 7)
      ? [{ iso: p.date, left: (k / Math.max(1, history.length - 1)) * 100 }]
      : [],
  ).filter((m) => m.left < 92);
  const monthFmt = new Intl.DateTimeFormat(lang, { month: "short", timeZone: "UTC" });

  return (
    <li className="flex flex-col rounded-xl border bg-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <label htmlFor={`name-${id}`} className="sr-only">
            {t("st.accountName")}
          </label>
          <div className="group relative flex max-w-[16rem] items-center">
            <Input
              id={`name-${id}`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => renameAccount(id, name)}
              onKeyDown={(e) => {
                if (e.key === "Enter") (e.target as HTMLInputElement).blur();
              }}
              className="h-9 -ml-2 rounded-md border-transparent bg-transparent px-2 pr-8 font-display text-lg font-semibold shadow-none transition-colors hover:border-input focus-visible:border-primary focus-visible:bg-background"
            />
            <Pencil className="pointer-events-none absolute right-2 size-3.5 text-muted-foreground/70 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100" aria-hidden />
          </div>
          <p className="text-xs text-muted-foreground">
            {manual ? t(fromEmail ? "st.fromEmails" : "st.enteredByYou") : `${t("count.files", { n: files.length })}, ${t("count.tx", { n: txCount })}`}, {analysis.currency}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-xs text-muted-foreground">{t("st.closing")}</p>
          <Money value={closing} className="font-display text-2xl font-semibold tracking-tight" />
        </div>
      </div>

      {history.length > 1 && (
        <div className="mt-4">
          <MiniArea values={history.map((p) => p.cents)} className="h-16" label={t("st.balanceTrend", { name })} />
          <div className="relative mt-1.5 h-4 text-[11px] text-muted-foreground" aria-hidden>
            {months.map((m) => (
              <span key={m.iso} className="absolute whitespace-nowrap" style={{ left: `${m.left}%` }}>
                {monthFmt.format(new Date(`${m.iso}T00:00:00Z`))}
              </span>
            ))}
          </div>
        </div>
      )}

      {manual ? (
        <p className="mt-3 border-t pt-3 text-xs text-muted-foreground">{t(fromEmail ? "st.emailNote" : "st.manualNote")}</p>
      ) : (
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t pt-3 text-xs">
        {gaps.length > 0 ? (
          <span className="font-medium text-warning-text">{t("st.gap", { ranges: gaps.join(t("st.and")) })}</span>
        ) : (
          <span className="inline-flex items-center gap-1 font-medium text-good-text">
            <CheckCircle2 className="size-3.5" aria-hidden />
            {t("st.connectedShort")}
          </span>
        )}
        {accountRejected.length > 0 && (
          <span className="inline-flex items-center gap-1.5 font-medium text-warning-text">
            <span className="inline-block size-1.5 rounded-full bg-warning" aria-hidden />
            {t("st.flagged", { n: accountRejected.length })}
          </span>
        )}
        <span className="ml-auto text-muted-foreground">
          {files.map((f) => t("common.range", { from: formatDate(f.start), to: formatDate(f.end) })).join(", ")}
        </span>
      </div>
      )}
    </li>
  );
}

function Results({
  analysis: initialAnalysis,
  sample,
}: {
  analysis: CashAnalysis;
  sample: boolean;
}) {
  const { clearData, accountNames, setLive, source, update } = useWorkspace();

  const { t } = useT();

  const [analysis, setAnalysis] = useState<CashAnalysis>(initialAnalysis);

  const [repairNotice, setRepairNotice] = useState<string | null>(null);

  // Modal edit state for rejected row

  const [editingRow, setEditingRow] = useState<RejectedRow | null>(null);

  const [editDate, setEditDate] = useState("");

  const [editAmount, setEditAmount] = useState("");

  const [editDesc, setEditDesc] = useState("");

  const [editId, setEditId] = useState("");

  const [editError, setEditError] = useState<string | null>(null);

  useEffect(() => {
    setAnalysis(initialAnalysis);
  }, [initialAnalysis]);

  const totalSpend = SPENDING.reduce((sum, s) => sum + s.cents, 0);

  const maxSpend = Math.max(...SPENDING.map((s) => s.cents), 1);

  const { files } = layout(analysis, sample);

  const accounts = Array.from(new Set(files.map((f) => f.account_id)));
  const manual = analysis.document_format === "MANUAL";

  // Each account's daily balance, from the sample series or what /analyze returned.
  const accountHistory = (id: string) =>
    ((sample ? SERIES : analysis.account_history ?? []).find((x) => x.account_id === id)?.points ?? [])
      .filter((p) => p.balance !== null)
      .map((p) => ({ date: p.date, cents: stringToCents(p.balance as string) }));

  const transfers = analysis.internal_transfers ?? [];

  const closingNum = parseFloat(analysis.current_balance || "0");

  const netChangeNum = parseFloat(analysis.net_period_change || "0");

  const openingNum = closingNum - netChangeNum;

  const handleRepairRow = (
    rowNumber: number,

    fix: {
      posted_on?: string;
      amount?: string;
      description?: string;
      transaction_id?: string;
    },

    notice: string,
  ) => {
    setAnalysis((prev) => {
      const remaining = prev.rejected_rows.filter(
        (r) => r.row_number !== rowNumber,
      );

      const deltaAmount = fix.amount ? parseFloat(fix.amount) : 0;

      const currentVal = parseFloat(prev.current_balance || "0");

      const updatedBalance = (currentVal + deltaAmount).toFixed(2);

      const nextAnalysis: CashAnalysis = {
        ...prev,

        accepted_count: prev.accepted_count + 1,

        rejected_rows: remaining,

        current_balance: updatedBalance,
      };

      setLive({ analysis: nextAnalysis });

      if (source !== "live") {
        update({ hasData: true, source: "live" });
      }

      return nextAnalysis;
    });

    setRepairNotice(notice);

    setTimeout(() => setRepairNotice(null), 4500);
  };

  const handleExcludeDuplicate = (r: RejectedRow) => {
    setAnalysis((prev) => {
      const remaining = prev.rejected_rows.filter(
        (row) => row.row_number !== r.row_number,
      );

      const nextAnalysis: CashAnalysis = {
        ...prev,

        rejected_rows: remaining,
      };

      setLive({ analysis: nextAnalysis });

      if (source !== "live") {
        update({ hasData: true, source: "live" });
      }

      return nextAnalysis;
    });

    setRepairNotice(
      t("st.nExcluded", { n: r.row_number }),
    );

    setTimeout(() => setRepairNotice(null), 4500);
  };

  const handleNormalizeDate = (r: RejectedRow) => {
    if (!r.suggested_fix) return;

    handleRepairRow(
      r.row_number,

      r.suggested_fix,

      t("st.nNormalized", { n: r.row_number, date: formatDate(r.suggested_fix.posted_on) }),
    );
  };

  const handleResolveAll = () => {
    const count = (analysis?.rejected_rows ?? []).length;

    setAnalysis((prev) => {
      let balanceDelta = 0;

      let addedCount = 0;

      for (const r of prev.rejected_rows) {
        if (r.reason_code === "DUPLICATE_TRANSACTION_ID") {
          continue;
        }

        if (r.suggested_fix?.amount) {
          balanceDelta += parseFloat(r.suggested_fix.amount);

          addedCount += 1;
        }
      }

      const currentVal = parseFloat(prev.current_balance || "0");

      const updatedBalance = (currentVal + balanceDelta).toFixed(2);

      const nextAnalysis: CashAnalysis = {
        ...prev,

        accepted_count: prev.accepted_count + addedCount,

        rejected_rows: [],

        current_balance: updatedBalance,
      };

      setLive({ analysis: nextAnalysis });

      if (source !== "live") {
        update({ hasData: true, source: "live" });
      }

      return nextAnalysis;
    });

    setRepairNotice(
      t("st.nAll", { n: count }),
    );

    setTimeout(() => setRepairNotice(null), 4500);
  };

  const handleQuickFix = (r: RejectedRow) => {
    if (!r.suggested_fix) return;

    handleRepairRow(
      r.row_number,
      r.suggested_fix,
      t("st.nFixed", { n: r.row_number }),
    );
  };

  const openEditModal = (r: RejectedRow) => {
    setEditingRow(r);

    setEditDate(r.suggested_fix?.posted_on ?? "");

    setEditAmount(r.suggested_fix?.amount ?? "");

    setEditDesc(r.suggested_fix?.description ?? "");

    setEditId(r.suggested_fix?.transaction_id ?? `tx_${r.row_number}`);

    setEditError(null);
  };

  const saveEditModal = () => {
    if (!editingRow) return;

    const cleanDate = editDate.trim();

    const cleanAmount = editAmount.trim();

    if (!/^\d{4}-\d{2}-\d{2}$/.test(cleanDate)) {
      setEditError(t("st.errDate"));

      return;
    }

    if (isNaN(parseFloat(cleanAmount))) {
      setEditError(t("st.errAmount"));

      return;
    }

    handleRepairRow(
      editingRow.row_number,

      {
        posted_on: cleanDate,
        amount: cleanAmount,
        description: editDesc.trim(),
        transaction_id: editId.trim(),
      },

      t("st.nEdited", { n: editingRow.row_number }),
    );

    setEditingRow(null);
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={fade}
      className="space-y-10"
    >
      <section>
        <SectionTitle aside={manual ? undefined : t("count.files", { n: files.length })}>
          {t("st.accounts")}
        </SectionTitle>

        <ul className={cn("grid gap-4", accounts.length > 1 && "lg:grid-cols-2")}>
          {accounts.map((id) => (
            <AccountRow
              key={id}
              id={id}
              files={files}
              analysis={analysis}
              history={accountHistory(id)}
            />
          ))}
        </ul>
      </section>

      <EntriesLedger />

      {/* Transfers, rows set aside and spending describe a statement; typed-in figures have none. */}
      {!manual && (
        <>
      <div className="grid gap-6 [&>*]:min-w-0">
        {transfers.length > 0 && (
          <section className="rounded-xl border bg-card p-5 md:p-6">
            <SectionTitle
              aside={
                <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary figures">
                  {t("st.excluded", { amount: formatMoney(analysis.internal_transfers_excluded ?? "0") })}
                </span>
              }
            >
              <div className="flex items-center gap-2">
                
                <span>{t("st.transfers")}</span>
              </div>
            </SectionTitle>

            <p className="mb-4 text-xs sm:text-sm text-muted-foreground">
              {t("st.transfersNote")}
            </p>

            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="border-border/60 hover:bg-transparent">
                    <TableHead className="w-[85px] text-xs">
                      {t("col.date")}
                    </TableHead>

                    <TableHead className="text-xs">{t("st.flow")}</TableHead>

                    <TableHead className="w-[110px] text-right text-xs">
                      {t("col.amount")}
                    </TableHead>
                  </TableRow>
                </TableHeader>

                <TableBody>
                  {transfers.map((x) => (
                    <TableRow
                      key={x.outflow_tx_id}
                      className="border-border/40"
                    >
                      <TableCell className="figures text-xs text-muted-foreground py-2.5">
                        {formatDate(x.transfer_date)}
                      </TableCell>

                      <TableCell className="py-2.5">
                        <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                          <span className="truncate max-w-[110px] sm:max-w-none">
                            {accountNames[x.outflow_account] ??
                              x.outflow_account}
                          </span>

                          <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />

                          <span className="truncate max-w-[110px] sm:max-w-none">
                            {accountNames[x.inflow_account] ?? x.inflow_account}
                          </span>
                        </div>
                      </TableCell>

                      <TableCell className="text-right py-2.5">
                        <Money
                          value={x.amount}
                          className="font-semibold text-foreground text-xs"
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </section>
        )}

        <section
          className={cn(
            "rounded-xl border bg-card p-5 md:p-6",
            transfers.length === 0 && "lg:col-span-2",
          )}
        >
          <SectionTitle
            aside={
              <div className="flex items-center gap-2">
                {(analysis?.rejected_rows ?? []).length > 0 ? (
                  <>
                    <span className="rounded-md border border-warning/30 bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning-text figures">
                      {t("st.pending", { n: (analysis?.rejected_rows ?? []).length })}
                    </span>

                    <Button
                      size="sm"

                      variant="outline"

                      className="h-7 px-2.5 text-xs border-primary/40 text-primary hover:bg-primary/10 gap-1.5 font-medium shadow-2xs"

                      onClick={handleResolveAll}

                      title={t("st.resolveAllTitle")}
                    >
                      <CheckCheck className="h-3.5 w-3.5" />

                      <span>{t("st.resolveAll")}</span>
                    </Button>
                  </>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-md border border-good/30 bg-good/10 px-2 py-0.5 text-xs font-medium text-good-text">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    {t("st.allClear")}
                  </span>
                )}
              </div>
            }
          >
            <div className="flex items-center gap-2">
              
              <span>{t("st.rejected")}</span>
            </div>
          </SectionTitle>

          <AnimatePresence>
            {repairNotice && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}

                animate={{ opacity: 1, height: "auto" }}

                exit={{ opacity: 0, height: 0 }}

                className="mb-3.5 flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 text-xs font-medium text-primary"
              >
                <CheckCheck className="h-3.5 w-3.5 shrink-0" />

                <span>{repairNotice}</span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Statement Tie-Out & Opening Reserves Strip */}

          <div className="mb-5 border-y py-4">
            <div className="grid grid-cols-3 gap-4">
              <div>
                <span className="block text-xs text-muted-foreground">
                  {t("st.opening")}
                </span>

                <span className="text-base font-semibold text-foreground figures">
                  {formatMoney(openingNum.toFixed(2))}
                </span>
              </div>

              <div>
                <span className="block text-xs text-muted-foreground">
                  {t("st.net")}
                </span>

                <span
                  className={cn(
                    "text-base font-semibold figures",
                    netChangeNum >= 0 ? "text-good-text" : "text-critical-text",
                  )}
                >
                  {netChangeNum >= 0 ? "+" : ""}
                  {formatMoney(netChangeNum.toFixed(2))}
                </span>
              </div>

              <div>
                <span className="block text-xs text-muted-foreground">
                  {t("st.closing")}
                </span>

                <span className="text-base font-semibold text-foreground figures">
                  {formatMoney(closingNum.toFixed(2))}
                </span>
              </div>

            </div>
          </div>

          {(analysis?.rejected_rows ?? []).length > 0 ? (
            <>
              <p className="mb-4 text-xs sm:text-sm text-muted-foreground">
                {t("st.rejectedNote")}
              </p>

              <div className="overflow-x-auto">
                <Table className="w-full">
                  <TableHeader>
                    <TableRow className="border-border/60 hover:bg-transparent">
                      <TableHead className="w-[68px] text-xs px-2.5 py-2">
                        {t("col.row")}
                      </TableHead>

                      <TableHead className="w-[115px] text-xs px-2.5 py-2">
                        {t("col.reason")}
                      </TableHead>

                      <TableHead className="text-xs px-2.5 py-2">
                        {t("st.colEntry")}
                      </TableHead>

                      <TableHead className="w-[85px] text-right text-xs px-2.5 py-2">
                        {t("st.colImpact")}
                      </TableHead>

                      <TableHead className="w-[125px] text-right text-xs px-2.5 py-2">
                        <span className="sr-only">{t("st.colAction")}</span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>

                  <TableBody>
                    {(analysis?.rejected_rows ?? []).map((r) => {
                      const fix = r.suggested_fix;

                      const isDup =
                        r.reason_code === "DUPLICATE_TRANSACTION_ID";

                      const isDate = r.reason_code === "INVALID_DATE";

                      return (
                        <TableRow
                          key={r.row_number}
                          className="border-border/40"
                        >
                          <TableCell className="figures text-xs font-medium text-muted-foreground py-2.5 px-2.5">
                            {r.row_number}
                          </TableCell>

                          <TableCell className="text-xs py-2.5 px-2.5">
                            {isDup ? (
                              <span className="inline-flex items-center gap-1 font-medium text-[11px] px-1.5 py-0.5 rounded border whitespace-nowrap border-border bg-muted text-ink-2">
                                <CopyX className="h-3 w-3 shrink-0" />
                                {t("reason.DUPLICATE_TRANSACTION_ID")}
                              </span>
                            ) : isDate ? (
                              <span className="inline-flex items-center gap-1 font-medium text-[11px] px-1.5 py-0.5 rounded border whitespace-nowrap border-warning/30 bg-warning/10 text-warning-text">
                                <CalendarX2 className="h-3 w-3 shrink-0" />
                                {t("reason.INVALID_DATE")}
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 font-medium text-[11px] px-1.5 py-0.5 rounded border whitespace-nowrap border-critical/30 bg-critical/10 text-critical-text">
                                <AlertCircle className="h-3 w-3 shrink-0" />

                                {t(`reason.${r.reason_code}` as Key)}
                              </span>
                            )}
                          </TableCell>

                          <TableCell className="text-xs py-2.5 px-2.5">
                            <div className="flex flex-col min-w-0 max-w-[200px] sm:max-w-[320px]">
                              <span className="figures text-foreground font-medium text-xs truncate">
                                {fix?.posted_on ? formatDate(fix.posted_on, true) : t("st.unparsed")}

                                {fix?.description && (
                                  <span className="font-sans font-normal text-muted-foreground ml-1.5">
                                    • {fix.description}
                                  </span>
                                )}
                              </span>

                              <span className="text-[11px] text-muted-foreground truncate mt-0.5">
                                {t(isDup ? "st.dupNote" : isDate ? "st.dateNote" : "st.otherNote")}
                              </span>
                            </div>
                          </TableCell>

                          <TableCell className="text-right py-2.5 px-2.5 text-xs figures">
                            {isDup ? (
                              <span
                                className="text-muted-foreground"
                                title={t("st.dupImpactTitle")}
                              >
                                {formatMoney("0")}
                              </span>
                            ) : fix?.amount ? (
                              <span
                                className={cn(
                                  fix.amount.trim().startsWith("-")
                                    ? "text-critical-text"
                                    : "text-good-text",
                                )}
                              >
                                {formatMoney(fix.amount)}
                              </span>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>

                          <TableCell className="text-right py-2.5 px-2.5">
                            <div className="flex items-center justify-end gap-1.5">
                              {isDup ? (
                                <Button
                                  size="sm"

                                  variant="outline"

                                  className="h-7 px-2.5 text-xs gap-1 font-medium"

                                  onClick={() => handleExcludeDuplicate(r)}

                                  title={t("st.excludeTitle")}
                                >
                                  <Ban className="h-3 w-3" />

                                  <span>{t("st.excludeDup")}</span>
                                </Button>
                              ) : isDate && fix ? (
                                <Button
                                  size="sm"

                                  variant="outline"

                                  className="h-7 px-2.5 text-xs border-primary/30 text-primary hover:bg-primary/10 gap-1 font-medium shadow-2xs"

                                  onClick={() => handleNormalizeDate(r)}

                                  title={t("st.normalizeTitle")}
                                >
                                  <Check className="h-3 w-3" />

                                  <span>{t("st.acceptFormat")}</span>
                                </Button>
                              ) : fix ? (
                                <Button
                                  size="sm"

                                  variant="outline"

                                  className="h-7 px-2.5 text-xs border-primary/30 text-primary hover:bg-primary/10 gap-1 font-medium shadow-2xs"

                                  onClick={() => handleQuickFix(r)}
                                >
                                  <Check className="h-3 w-3" />

                                  <span>{t("st.applyFix")}</span>
                                </Button>
                              ) : null}

                              <Button
                                size="sm"

                                variant="ghost"

                                className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground hover:bg-accent shrink-0"

                                onClick={() => openEditModal(r)}

                                title={t("st.editRow")}
                              >
                                <Pencil className="h-3.5 w-3.5" />

                                <span className="sr-only">{t("st.editRow")}</span>
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </>
          ) : (
            <div className="mt-3 flex items-start gap-3 rounded-xl border border-good/20 bg-good/5 p-4 text-sm">
              <CheckCircle2 className="h-5 w-5 text-good-text shrink-0 mt-0.5" />

              <div className="min-w-0">
                <p className="font-medium text-foreground text-sm">
                  {t("st.cleanTitle")}
                </p>

                <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                  {t("st.cleanBody")}
                </p>
              </div>
            </div>
          )}

          {/* Inline Edit Modal */}

          <Dialog
            open={editingRow !== null}
            onOpenChange={(open) => !open && setEditingRow(null)}
          >
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Pencil className="h-4 w-4 text-primary" />

                  {t("st.reconcileTitle", { n: editingRow?.row_number ?? 0 })}
                </DialogTitle>

                <DialogDescription>{t("st.reconcileDesc")}</DialogDescription>
              </DialogHeader>

              <div className="space-y-4 py-2">
                {editingRow?.raw_line && (
                  <div className="rounded-lg bg-muted/50 p-2.5 text-xs">
                    <p className="text-muted-foreground font-mono text-[11px] mb-1">
                      {t("st.rawRow")}
                    </p>

                    <code className="text-foreground break-all">
                      {editingRow.raw_line}
                    </code>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground">
                      {t("col.date")}
                    </label>

                    <Input
                      type="text"

                      value={editDate}

                      onChange={(e) => setEditDate(e.target.value)}

                      placeholder="YYYY-MM-DD"

                      className="font-mono text-xs"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground">
                      {t("col.amount")}
                    </label>

                    <Input
                      type="text"

                      value={editAmount}

                      onChange={(e) => setEditAmount(e.target.value)}

                      placeholder="-100.00"

                      className="font-mono text-xs"
                    />
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-medium text-foreground">
                    {t("quickCash.descLabel")}
                  </label>

                  <Input
                    type="text"

                    value={editDesc}

                    onChange={(e) => setEditDesc(e.target.value)}

                    placeholder={t("quickCash.descPlaceholder")}

                    className="text-xs"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-medium text-foreground">
                    {t("st.txId")}
                  </label>

                  <Input
                    type="text"

                    value={editId}

                    onChange={(e) => setEditId(e.target.value)}

                    placeholder="tx_001"

                    className="font-mono text-xs"
                  />
                </div>
              </div>

              {editError && (
                <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs font-medium text-destructive">
                  {editError}
                </div>
              )}

              <DialogFooter className="gap-2 sm:gap-0 sm:justify-between">
                <Button
                  variant="outline"

                  size="sm"

                  className="text-destructive hover:bg-destructive/10 border-destructive/30"

                  onClick={() => {
                    if (editingRow) {
                      handleExcludeDuplicate(editingRow);

                      setEditingRow(null);
                    }
                  }}
                >
                  {t("st.excludeRow")}
                </Button>

                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setEditingRow(null)}
                  >
                    {t("quickCash.cancel")}
                  </Button>

                  <Button size="sm" onClick={saveEditModal} className="gap-1.5">
                    <Check className="h-3.5 w-3.5" />

                    {t("st.saveReconcile")}
                  </Button>
                </div>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </section>
      </div>

      {/* Spending by category / Outflow Breakdown */}

      <section className="rounded-xl border bg-card p-5 md:p-6">
        <SectionTitle
          aside={
            sample ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
                {t("common.range", {
                  from: formatDate(analysis.start_date!),
                  to: formatDate(analysis.end_date!),
                })}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
                {t("fig.out")}:{" "}
                <Money
                  value={
                    analysis.operational_outflows ??
                    analysis.gross_outflows ??
                    "0"
                  }
                />
              </span>
            )
          }
        >
          <div className="flex items-center gap-2">
            
            <span>{t("st.spend")}</span>
          </div>
        </SectionTitle>

        {sample ? (
          <>
            <p className="mb-5 max-w-2xl text-xs sm:text-sm text-muted-foreground">
              {t("st.spendNote")}
            </p>

            <div className="flex flex-col items-center gap-8 md:flex-row md:items-center">
            <Donut
              segments={SPENDING.map((x) => ({ key: x.category, label: t(`cat.${x.category}` as Key), value: x.cents, color: CATEGORY_COLORS[x.category] ?? 'rgb(var(--muted-foreground))' }))}
              label={t("st.spend")}
              size={176}
            >
              <span className="text-xs text-muted-foreground">{t("fig.out")}</span>
              <Money value={centsToString(totalSpend)} cents={false} className="font-display text-xl font-semibold" />
            </Donut>
            <ul className="w-full flex-1 space-y-3.5">
              {SPENDING.map((s) => {
                const pct =
                  totalSpend > 0
                    ? ((s.cents / totalSpend) * 100).toFixed(1)
                    : "0";

                return (
                  <li
                    key={s.category}
                    className="grid grid-cols-[110px_1fr_135px] sm:grid-cols-[140px_1fr_150px] items-center gap-3 sm:gap-4 text-xs sm:text-sm"
                  >
                    <span className="font-medium text-foreground truncate">
                      {t(`cat.${s.category}` as Key)}
                    </span>

                    <div className="relative h-2 w-full overflow-hidden rounded-full bg-muted/80">
                      <motion.div
                        className="absolute inset-y-0 left-0 rounded-full"
                        style={{ background: CATEGORY_COLORS[s.category] ?? 'rgb(var(--primary))' }}

                        initial={{ width: 0 }}

                        animate={{ width: `${(s.cents / maxSpend) * 100}%` }}

                        transition={spring.gentle}
                      />
                    </div>

                    <div className="flex items-baseline justify-end gap-2 text-right">
                      <Money
                        value={s.amount}
                        className="font-semibold text-foreground"
                      />

                      <span className="w-12 text-right text-xs text-muted-foreground figures">
                        {pct}%
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
            </div>
          </>
        ) : analysis.recurring_obligations &&
          analysis.recurring_obligations.length > 0 ? (
          <>
            <p className="mb-5 max-w-2xl text-xs sm:text-sm text-muted-foreground">
              {t("st.recurringNote")}
            </p>

            <ul className="space-y-3.5">
              {analysis.recurring_obligations.map((ob) => {
                const amtNum = parseFloat(ob.amount || "0");

                const totalOut = parseFloat(
                  analysis.operational_outflows ??
                    analysis.gross_outflows ??
                    "1",
                );

                const pctVal =
                  totalOut > 0 ? ((amtNum / totalOut) * 100).toFixed(1) : "0";

                const label = t(ob.category === "PAYROLL" ? "cat.payroll" : ob.category === "RENT" ? "cat.rent" : "cat.debt");

                return (
                  <li
                    key={ob.category}
                    className="grid grid-cols-[120px_1fr_135px] sm:grid-cols-[160px_1fr_150px] items-center gap-3 sm:gap-4 text-xs sm:text-sm"
                  >
                    <div className="min-w-0">
                      <span className="font-medium text-foreground truncate block">
                        {label}
                      </span>

                      <span className="text-[11px] text-muted-foreground">
                        {t("st.dayMonthly", { n: ob.day_of_month })}
                      </span>
                    </div>

                    <div className="relative h-2 w-full overflow-hidden rounded-full bg-muted/80">
                      <motion.div
                        className="absolute inset-y-0 left-0 rounded-full bg-primary"

                        initial={{ width: 0 }}

                        animate={{
                          width: `${Math.min(100, (amtNum / (totalOut || 1)) * 100)}%`,
                        }}

                        transition={spring.gentle}
                      />
                    </div>

                    <div className="flex items-baseline justify-end gap-2 text-right">
                      <Money
                        value={ob.amount}
                        className="font-semibold text-foreground"
                      />

                      <span className="w-12 text-right text-xs text-muted-foreground figures">
                        {pctVal}%
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 rounded-xl border border-border/50 bg-background/50 p-4 text-sm">
            <div>
              <p className="text-xs text-muted-foreground">
                {t("fig.out")}
              </p>

              <Money
                value={
                  analysis.operational_outflows ??
                  analysis.gross_outflows ??
                  "0"
                }
                className="text-base font-semibold text-foreground"
              />

              <p className="text-[11px] text-muted-foreground mt-0.5">
                {t("fig.ownNote")}
              </p>
            </div>

            <div>
              <p className="text-xs text-muted-foreground">{t("fig.in")}</p>

              <Money
                value={analysis.gross_inflows ?? "0"}
                className="text-base font-semibold text-good-text"
              />

              <p className="text-[11px] text-muted-foreground mt-0.5">
                {t("st.beforeTransfers")}
              </p>
            </div>

            <div>
              <p className="text-xs text-muted-foreground">{t("fig.burn")}</p>

              <Money
                value={analysis.average_daily_burn}
                className="text-base font-semibold text-foreground"
              />

              <p className="text-[11px] text-muted-foreground mt-0.5">
                {analysis.runway_days === null ? t("quickCash.noBurn") : t("st.runwayDays", { n: analysis.runway_days })}
              </p>
            </div>
          </div>
        )}
      </section>
        </>
      )}

      <section className="border-t pt-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:p-5">
          <div className="min-w-0">
            <p className="text-sm font-medium text-destructive">
              {t("st.removeTitle")}
            </p>

            <p className="mt-0.5 text-xs text-muted-foreground">
              {t("st.removeBody")}
            </p>
          </div>

          <Dialog>
            <DialogTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="shrink-0 border-destructive/30 text-destructive hover:bg-destructive/10"
              >
                {t("st.remove")}
              </Button>
            </DialogTrigger>

            <DialogContent>
              <DialogHeader>
                <DialogTitle>{t("st.removeTitle")}</DialogTitle>

                <DialogDescription>{t("st.removeBody")}</DialogDescription>
              </DialogHeader>

              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="outline">{t("st.keep")}</Button>
                </DialogClose>

                <DialogClose asChild>
                  <Button variant="destructive" onClick={clearData}>
                    {t("st.remove")}
                  </Button>
                </DialogClose>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </section>
    </motion.div>
  );
}

type Incoming = { kind: "sample" } | { kind: "live"; files: File[] };

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
      <PageHeader
        title={t("nav.statements")}

        description={t("st.desc")}

      />

      <div className="space-y-10">
        <AnimatePresence mode="wait" initial={false}>
          {incoming?.kind === "live" ? (
            <LiveAnalyzing
              key="live"
              files={incoming.files}
              onDone={() => setIncoming(null)}
              onCancel={() => setIncoming(null)}
            />
          ) : incoming?.kind === "sample" ? (
            <SampleAnalyzing
              key="sample"

              onDone={() => {
                loadSample();

                setIncoming(null);
              }}
            />
          ) : state.status === "ready" ? (
            <motion.div
              key="compact-drop"
              exit={{ opacity: 0 }}
              transition={fade}
            >
              <CompactDropzone
                onFiles={(files) => setIncoming({ kind: "live", files })}
              />
            </motion.div>
          ) : (
            <motion.div key="drop" exit={{ opacity: 0 }} transition={fade}>
              <Dropzone
                onFiles={(files) => setIncoming({ kind: "live", files })}
              />

              {/* Direct entry or sample company */}

              <div className="mt-3 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-center text-sm text-muted-foreground">
                <QuickCashDialog
                  defaultMode="SET_BALANCE"

                  trigger={
                    <button
                      type="button"
                      className="py-2 font-medium text-foreground underline underline-offset-2"
                    >
                      {t("quickCash.triggerDirect")}
                    </button>
                  }
                />

                {(state.status === "empty" || source === "live") && (
                  <span>
                    <span aria-hidden className="mr-3">
                      •
                    </span>
                    {t(
                      state.status === "empty"
                        ? "st.noFiles"
                        : "lv.showingYours",
                    )}{" "}
                    <button
                      type="button"
                      onClick={() => setIncoming({ kind: "sample" })}
                      className="py-2 font-medium text-foreground underline underline-offset-2"
                    >
                      {t("st.useSample")}
                    </button>
                  </span>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {!incoming && state.status === "loading" && <LoadingBlock rows={4} />}

        {!incoming && state.status === "error" && (
          <ErrorState message={state.message} retry={state.retry} />
        )}

        {!incoming && state.status === "ready" && (
          <Results analysis={state.data} sample={source === "sample"} />
        )}
      </div>
    </div>
  );
}
