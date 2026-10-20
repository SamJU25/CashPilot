'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  Check,
  Download,
  Heart,
  Loader2,
  RotateCw,
  Search,
  Trash2,
  Wrench,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ApiError, api, type Hardware, type HFDownload, type HFFile, type HFRepo, type LocalModel } from '@/lib/api';
import { RUNTIME_OVERHEAD_GB, fitFor, formatBytes, formatContext, formatCount, formatParams, modelLabel, useInstalledModels, type Fit } from '@/lib/local-models';
import { useWorkspace } from '@/lib/workspace';
import { useT, type Key } from '@/lib/i18n';
import { cn } from '@/lib/utils';

const ACTIVE = new Set(['queued', 'downloading']);
// `server` sorts run on Hugging Face; name and size reorder the popular results here.
const SORTS: { id: string; label: Key; server: string; compare?: (a: HFRepo, b: HFRepo) => number }[] = [
  { id: 'popular', label: 'lm.sortPopular', server: 'popular' },
  { id: 'trending', label: 'lm.sortTrending', server: 'trending' },
  { id: 'latest', label: 'lm.sortLatest', server: 'latest' },
  { id: 'newest', label: 'lm.sortNewest', server: 'newest' },
  { id: 'liked', label: 'lm.sortLiked', server: 'liked' },
  { id: 'name', label: 'lm.sortName', server: 'popular', compare: (a, b) => a.name.localeCompare(b.name, 'en', { numeric: true }) },
  // Unknown parameter counts sort last.
  { id: 'size', label: 'lm.sortSize', server: 'popular', compare: (a, b) => (a.parameters ?? Infinity) - (b.parameters ?? Infinity) },
];

function Chip({ children, tone = 'neutral', className }: { children: React.ReactNode; tone?: 'neutral' | 'good' | 'accent'; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded border px-1.5 py-px text-[11px] font-medium leading-4',
        tone === 'good' && 'border-good/30 bg-good/10 text-good-text',
        tone === 'accent' && 'border-primary/30 bg-primary/10 text-primary',
        tone === 'neutral' && 'border-border bg-muted/60 text-ink-2',
        className,
      )}
    >
      {children}
    </span>
  );
}

function ToolsChip({ value }: { value?: string | null }) {
  const { t } = useT();
  if (!value) return null;
  return (
    <Chip tone="good">
      <Wrench className="size-3" aria-hidden />
      {t('lm.tools')}
    </Chip>
  );
}

function Progress({ job }: { job: HFDownload }) {
  const { t } = useT();
  const pct = job.total_bytes ? Math.min(100, (job.downloaded_bytes / job.total_bytes) * 100) : null;
  return (
    <div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct ?? undefined} aria-label={t('lm.downloadingFile', { name: job.filename })}>
        <div className={cn('h-full rounded-full bg-primary transition-[width] duration-200', pct === null && 'w-1/3 animate-pulse')} style={pct === null ? undefined : { width: `${pct}%` }} />
      </div>
      <p className="figures mt-1 text-[11px] text-muted-foreground">
        {job.status === 'queued'
          ? t('lm.starting')
          : t(pct !== null ? 'lm.progressPct' : 'lm.progress', { done: formatBytes(job.downloaded_bytes), total: formatBytes(job.total_bytes), pct: Math.floor(pct ?? 0) })}
      </p>
    </div>
  );
}

/** Polls download jobs while any is running; calls onFinished once per completed job. */
function useDownloads(onFinished: (job: HFDownload) => void) {
  const [jobs, setJobs] = useState<HFDownload[]>([]);
  const seen = useRef<Set<string> | null>(null);
  const finished = useRef(onFinished);
  finished.current = onFinished;

  const poll = useCallback(async () => {
    try {
      const list = await api.hfDownloads();
      setJobs(list);
      const done = list.filter((j) => j.status === 'completed');
      // Jobs that finished before this page opened are not news.
      if (seen.current === null) seen.current = new Set(done.map((j) => j.job_id));
      for (const j of done) {
        if (!seen.current.has(j.job_id)) {
          seen.current.add(j.job_id);
          finished.current(j);
        }
      }
      return list.some((j) => ACTIVE.has(j.status));
    } catch {
      return false;
    }
  }, []);

  const [tick, setTick] = useState(0);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let alive = true;
    const loop = async () => {
      const running = await poll();
      if (alive && running) timer = setTimeout(loop, 1000);
    };
    void loop();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [poll, tick]);

  return { jobs, kick: () => setTick((t) => t + 1) };
}

function InstalledRow({ model, active, onSelect, onDelete }: { model: LocalModel; active: boolean; onSelect: () => void; onDelete: () => void }) {
  const { t } = useT();
  return (
    <div className={cn('flex items-center gap-3 px-3 py-2.5 transition-colors', active ? 'bg-primary/5' : 'hover:bg-muted/40')}>
      <button
        type="button"
        role="radio"
        aria-checked={active}
        onClick={onSelect}
        className="flex min-w-0 flex-1 items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-sm"
      >
        <span className={cn('grid size-4 shrink-0 place-items-center rounded-full border', active ? 'border-primary bg-primary text-primary-foreground' : 'border-input')} aria-hidden>
          {active && <Check className="size-3" strokeWidth={3} />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="truncate text-sm font-medium">{modelLabel(model)}</span>
            {model.quant && <Chip className="font-mono">{model.quant}</Chip>}
            <ToolsChip value={model.tool_calling} />
            {active && <Chip tone="accent">{t('lm.inUse')}</Chip>}
          </span>
          <span className="mt-0.5 block truncate text-xs text-muted-foreground">
            <span className="figures">{model.size_gb ? `${model.size_gb} GB` : '—'}</span>
            {model.repo_id?.includes('/') && <> · {model.repo_id}</>}
          </span>
        </span>
      </button>
      <Button variant="ghost" size="icon" className="size-8 shrink-0 text-muted-foreground hover:text-critical-text" onClick={onDelete} aria-label={t('lm.deleteAria', { name: modelLabel(model) })}>
        <Trash2 className="size-4" />
      </Button>
    </div>
  );
}

const FIT_LABEL: Record<Fit, { text: Key; title: Key; className: string }> = {
  gpu: { text: 'lm.fitGpu', title: 'lm.fitGpuTitle', className: 'text-good-text' },
  split: { text: 'lm.fitSplit', title: 'lm.fitSplitTitle', className: 'text-ink-2' },
  memory: { text: 'lm.fitMemory', title: 'lm.fitMemoryTitle', className: 'text-warning-text' },
};

function FitTag({ fit }: { fit: Fit | null }) {
  const { t } = useT();
  if (!fit) return <span className="w-20 shrink-0" aria-hidden />;
  const f = FIT_LABEL[fit];
  return <span className={cn('w-20 shrink-0 text-xs font-medium', f.className)} title={t(f.title)}>{t(f.text)}</span>;
}

function MemoryMeter({ label, detail, total, free }: { label: string; detail?: string | null; total: number; free: number }) {
  const { t } = useT();
  const used = Math.min(total, Math.max(0, total - free));
  const pct = total > 0 ? (used / total) * 100 : 0;
  // Near-full memory is the state worth flagging; the label below says it in words too.
  const high = pct >= 90;
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 text-xs">
        <span className="min-w-0 truncate font-medium text-foreground">{label}</span>
        <span className="figures shrink-0 text-ink-2">
          {t('lm.memFree', { free: free.toFixed(1), total: total.toFixed(1) })}{high && <span className="text-warning-text">{t('lm.almostFull')}</span>}
        </span>
      </div>
      <div
        role="meter"
        aria-label={t('lm.memInUse', { label })}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={Number(used.toFixed(1))}
        aria-valuetext={t('lm.memValue', { used: used.toFixed(1), free: free.toFixed(1), total: total.toFixed(1) })}
        className={cn('mt-1.5 h-2 overflow-hidden rounded-full', high ? 'bg-warning/20' : 'bg-primary/15')}
      >
        <div className={cn('h-full rounded-full transition-[width] duration-300', high ? 'bg-warning' : 'bg-primary')} style={{ width: `${pct}%` }} />
      </div>
      {detail && <p className="mt-1 truncate text-[11px] text-muted-foreground">{detail}</p>}
    </div>
  );
}

export function HardwarePanel({ hw, onRefresh }: { hw: Hardware | null | undefined; onRefresh: () => void }) {
  const { t, rich } = useT();
  const amount = (gb: number) => <span className="figures font-medium text-foreground">{gb.toFixed(1)} GB</span>;
  const gpuRoom = hw?.vram_free_gb != null ? Math.max(0, hw.vram_free_gb - RUNTIME_OVERHEAD_GB) : null;
  const ramRoom = hw?.ram_available_gb != null ? Math.max(0, hw.ram_available_gb - RUNTIME_OVERHEAD_GB) : null;
  return (
    <div className="rounded-lg border px-4 py-3.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{t('lm.freeNow')}</p>
        <Button variant="ghost" size="sm" className="-mr-2 h-7 gap-1.5 px-2 text-xs text-muted-foreground" onClick={onRefresh} disabled={hw === undefined}>
          <RotateCw className="size-3" aria-hidden /> {t('lm.refresh')}
        </Button>
      </div>

      {hw === undefined && (
        <div className="mt-3 space-y-4" aria-busy="true" aria-label={t('lm.readingMemory')}>
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-full" />
        </div>
      )}

      {hw === null && <p className="mt-2 text-xs text-muted-foreground">{t('lm.hwError')}</p>}

      {hw && (
        <div className="mt-3 space-y-4">
          {hw.vram_total_gb != null && hw.vram_free_gb != null ? (
            <MemoryMeter label={t('lm.gpuMemory')} detail={hw.gpu_name} total={hw.vram_total_gb} free={hw.vram_free_gb} />
          ) : (
            <p className="text-xs text-muted-foreground">{t('lm.noGpu')}</p>
          )}
          {hw.ram_total_gb != null && hw.ram_available_gb != null && (
            <MemoryMeter label={t('lm.ramMemory')} total={hw.ram_total_gb} free={hw.ram_available_gb} />
          )}
          <p className="text-xs text-muted-foreground">
            {gpuRoom !== null ? (
              <>
                {rich('lm.roomGpu', { size: amount(gpuRoom) })}
                {ramRoom !== null && rich('lm.roomSplit', { size: amount(gpuRoom + ramRoom) })}
              </>
            ) : ramRoom !== null ? (
              rich('lm.roomRam', { size: amount(ramRoom) })
            ) : null}
            {' '}{t('lm.reserved', { gb: RUNTIME_OVERHEAD_GB })}
          </p>
        </div>
      )}
    </div>
  );
}

function RepoFiles({ repo, jobs, hw, onDownload, onBack }: { repo: HFRepo; jobs: HFDownload[]; hw: Hardware | null | undefined; onDownload: (f: HFFile) => void; onBack: () => void }) {
  const { t } = useT();
  const [state, setState] = useState<{ status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; files: HFFile[]; message?: string | null }>({ status: 'loading' });

  const load = useCallback(async () => {
    setState({ status: 'loading' });
    try {
      const res = await api.hfFiles(repo.repo_id);
      setState(res.success ? { status: 'ready', files: res.files, message: res.message } : { status: 'error', message: res.message ?? t('lm.filesError') });
    } catch (e) {
      setState({ status: 'error', message: e instanceof ApiError ? e.message : t('lm.filesError') });
    }
  }, [repo.repo_id, t]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div>
      <div className="flex items-start gap-2">
        <Button variant="ghost" size="icon" className="-ml-2 size-8 shrink-0" onClick={onBack} aria-label={t('lm.back')}>
          <ArrowLeft className="size-4" />
        </Button>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{repo.name}</p>
          <p className="truncate text-xs text-muted-foreground">{t('lm.pickQuant', { author: repo.author })}</p>
        </div>
      </div>
      <div className="mt-3 max-h-[52vh] overflow-y-auto rounded-md border">
        {state.status === 'loading' && (
          <div className="space-y-2 p-3" aria-busy="true">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-9 w-full" />)}
          </div>
        )}
        {state.status === 'error' && (
          <div role="alert" className="flex items-center justify-between gap-3 p-4 text-sm">
            <span className="text-critical-text">{state.message}</span>
            <Button variant="outline" size="sm" onClick={() => void load()}>
              <RotateCw className="size-3.5" /> {t('lm.retry')}
            </Button>
          </div>
        )}
        {state.status === 'ready' && state.files.length === 0 && <p className="p-6 text-center text-sm text-muted-foreground">{state.message ?? t('lm.noFiles')}</p>}
        {state.status === 'ready' && state.files.length > 0 && (
          <ul className="divide-y">
            {state.files.map((f) => {
              const job = jobs.find((j) => j.filename === f.filename && ACTIVE.has(j.status));
              const done = f.installed || jobs.some((j) => j.filename === f.filename && j.status === 'completed');
              return (
                <li key={f.filename} className="px-3 py-2">
                  <div className="flex items-center gap-3">
                    <span className="w-20 shrink-0 font-mono text-xs font-semibold">{f.quant ?? '—'}</span>
                    <span className="figures w-16 shrink-0 text-xs text-ink-2">{formatBytes(f.size_bytes)}</span>
                    <FitTag fit={fitFor(f.size_bytes, hw)} />
                    <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground" title={f.filename}>
                      {f.recommended && <Chip tone="accent" className="mr-1.5">{t('lm.recommended')}</Chip>}
                      {f.filename}
                    </span>
                    {done ? (
                      <Chip tone="good"><Check className="size-3" aria-hidden /> {t('lm.installed')}</Chip>
                    ) : job ? (
                      <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => void api.hfCancel(job.job_id)}>
                        <X className="size-3.5" /> {t('lm.cancel')}
                      </Button>
                    ) : (
                      <Button variant={f.recommended ? 'default' : 'outline'} size="sm" className="h-7 text-xs" onClick={() => onDownload(f)}>
                        <Download className="size-3.5" /> {t('lm.download')}
                      </Button>
                    )}
                  </div>
                  {job && <div className="mt-2 pl-[15rem]"><Progress job={job} /></div>}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

function HuggingFaceBrowser({ open, onOpenChange, jobs, hw, onDownload }: { open: boolean; onOpenChange: (v: boolean) => void; jobs: HFDownload[]; hw: Hardware | null | undefined; onDownload: (repo: HFRepo, f: HFFile) => void }) {
  const { t, rich } = useT();
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('popular');
  const [repo, setRepo] = useState<HFRepo | null>(null);
  const [state, setState] = useState<
    | { status: 'loading' }
    | { status: 'error'; message: string }
    | { status: 'ready'; models: HFRepo[]; cursor: string | null; more: 'idle' | 'loading' | 'error' }
  >({ status: 'loading' });
  const reqId = useRef(0);
  const listRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const search = useCallback(async (q: string, sortId: string) => {
    const id = ++reqId.current;
    setState({ status: 'loading' });
    listRef.current?.scrollTo({ top: 0 });
    try {
      const res = await api.hfSearch(q, SORTS.find((x) => x.id === sortId)?.server ?? 'popular');
      if (id !== reqId.current) return;
      setState(res.success ? { status: 'ready', models: res.models, cursor: res.next_cursor ?? null, more: 'idle' } : { status: 'error', message: res.message ?? t('lm.searchFailed') });
    } catch (e) {
      if (id === reqId.current) setState({ status: 'error', message: e instanceof ApiError ? e.message : t('lm.searchFailed') });
    }
  }, [t]);

  const cursor = state.status === 'ready' ? state.cursor : null;
  const moreState = state.status === 'ready' ? state.more : 'idle';

  const loadMore = useCallback(async () => {
    if (!cursor || moreState === 'loading') return;
    const id = reqId.current;
    setState((s) => (s.status === 'ready' ? { ...s, more: 'loading' } : s));
    try {
      const res = await api.hfSearch(query, SORTS.find((x) => x.id === sort)?.server ?? 'popular', cursor);
      if (id !== reqId.current) return;
      setState((s) => {
        if (s.status !== 'ready') return s;
        if (!res.success) return { ...s, more: 'error' };
        // Hub pages can overlap when rankings shift between requests.
        const seen = new Set(s.models.map((m) => m.repo_id));
        return { ...s, models: [...s.models, ...res.models.filter((m) => !seen.has(m.repo_id))], cursor: res.next_cursor ?? null, more: 'idle' };
      });
    } catch {
      if (id === reqId.current) setState((s) => (s.status === 'ready' ? { ...s, more: 'error' } : s));
    }
  }, [cursor, moreState, query, sort]);

  // Fetch the next page when the end of the list scrolls into view (or is already visible on a short page).
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !cursor || moreState !== 'idle') return;
    const io = new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && void loadMore(), { root: listRef.current, rootMargin: '200px' });
    io.observe(el);
    return () => io.disconnect();
  }, [cursor, moreState, loadMore, repo]);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => void search(query, sort), query ? 350 : 0);
    return () => clearTimeout(t);
  }, [open, query, sort, search]);

  const compare = SORTS.find((x) => x.id === sort)?.compare;
  const sorted = state.status === 'ready' ? (compare ? [...state.models].sort(compare) : state.models) : [];

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) setRepo(null); }}>
      <DialogContent className="w-[calc(100%-2rem)] max-w-2xl grid-cols-[minmax(0,1fr)] gap-0 p-0">
        <DialogHeader className="border-b px-5 pb-4 pt-5">
          <DialogTitle>{t('lm.hfTitle')}</DialogTitle>
          <DialogDescription>{rich('lm.hfDesc', { folder: <code className="font-mono text-[12px]">models/</code> })}</DialogDescription>
        </DialogHeader>
        <div className="min-w-0 px-5 py-4">
          {repo ? (
            <RepoFiles repo={repo} jobs={jobs} hw={hw} onBack={() => setRepo(null)} onDownload={(f) => onDownload(repo, f)} />
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative min-w-[12rem] flex-1">
                  <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
                  <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('lm.searchPh')} className="pl-8" aria-label={t('lm.searchAria')} autoFocus />
                </div>
                <Select value={sort} onValueChange={setSort}>
                  <SelectTrigger className="h-9 w-[10rem] shrink-0 text-xs" aria-label={t('lm.sortAria')}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SORTS.map((x) => (
                      <SelectItem key={x.id} value={x.id} className="text-xs">{t(x.label)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">{t('lm.toolsOnly')}</p>
              <div ref={listRef} className="mt-3 max-h-[52vh] overflow-y-auto rounded-md border">
                {state.status === 'loading' && (
                  <div className="space-y-2 p-3" aria-busy="true" aria-label={t('lm.searching')}>
                    {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
                  </div>
                )}
                {state.status === 'error' && (
                  <div role="alert" className="flex items-center justify-between gap-3 p-4 text-sm">
                    <span className="text-critical-text">{state.message}</span>
                    <Button variant="outline" size="sm" onClick={() => void search(query, sort)}>
                      <RotateCw className="size-3.5" /> {t('lm.retry')}
                    </Button>
                  </div>
                )}
                {state.status === 'ready' && state.models.length === 0 && (
                  <p className="p-8 text-center text-sm text-muted-foreground">
                    {query ? t('lm.noResultsQuery', { q: query }) : t('lm.noResults')}
                  </p>
                )}
                {state.status === 'ready' && state.models.length > 0 && (
                  <ul className="divide-y">
                    {sorted.map((m) => (
                      <li key={m.repo_id}>
                        <button type="button" onClick={() => setRepo(m)} className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-none">
                          <span className="min-w-0 flex-1">
                            <span className="flex flex-wrap items-center gap-1.5">
                              <span className="truncate text-sm font-medium">{m.name}</span>
                              {formatParams(m.parameters) && <Chip className="figures">{formatParams(m.parameters)}</Chip>}
                              {formatContext(m.context_length) && <Chip className="figures">{formatContext(m.context_length)}</Chip>}
                            </span>
                            <span className="mt-0.5 block truncate text-xs text-muted-foreground">{m.author}{m.architecture ? ` · ${m.architecture}` : ''}</span>
                          </span>
                          <span className="figures hidden shrink-0 items-center gap-3 text-xs text-muted-foreground sm:flex">
                            <span className="inline-flex items-center gap-1" title={t('lm.downloads30')}><Download className="size-3" aria-hidden />{formatCount(m.downloads)}</span>
                            <span className="inline-flex items-center gap-1" title={t('lm.likes')}><Heart className="size-3" aria-hidden />{formatCount(m.likes)}</span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {state.status === 'ready' && state.models.length > 0 && (
                  <div ref={sentinelRef} className="border-t px-3 py-3 text-center text-xs text-muted-foreground" aria-live="polite">
                    {state.more === 'loading' ? (
                      <span className="inline-flex items-center gap-1.5"><Loader2 className="size-3.5 animate-spin" aria-hidden /> {t('lm.loadingMore')}</span>
                    ) : state.more === 'error' ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-critical-text">{t('lm.moreError')}</span>
                        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => void loadMore()}>{t('lm.retry')}</Button>
                      </span>
                    ) : state.cursor ? (
                      <span className="figures">{t('lm.loaded', { n: state.models.length })}</span>
                    ) : (
                      <span className="figures">{t('lm.allShown', { n: state.models.length })}</span>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Settings block for the Local GGUF provider: installed models, Hugging Face downloads and file import. */
export function LocalModelManager({ hw, onHardwareChange }: { hw: Hardware | null | undefined; onHardwareChange: () => void }) {
  const { localModel, update } = useWorkspace();
  const { t, rich } = useT();
  const { state, refresh } = useInstalledModels();
  const [browserOpen, setBrowserOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [toDelete, setToDelete] = useState<LocalModel | null>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkPath, setLinkPath] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const models = state.status === 'ready' ? state.models : [];
  const activeId = models.some((m) => m.id === localModel) ? localModel : models[0]?.id;

  // A stale selection (deleted file, old default) would send chat to a model that is not on disk.
  useEffect(() => {
    // With nothing installed a saved pick points at no file; clear it so chat and the chip stop naming it.
    if (state.status === 'ready' && (activeId ?? '') !== localModel) update({ localModel: activeId ?? '' });
  }, [state.status, activeId, localModel, update]);

  const { jobs, kick } = useDownloads((job) => {
    setNotice({ ok: true, text: t('lm.downloaded', { name: job.filename }) });
    onHardwareChange();
    void refresh().then(() => {
      if (!activeId) update({ localModel: job.model_id });
    });
  });
  const running = jobs.filter((j) => ACTIVE.has(j.status));
  const failed = jobs.filter((j) => j.status === 'failed').slice(0, 1);

  const startDownload = async (repo: HFRepo, f: HFFile) => {
    try {
      const res = await api.hfDownload(repo.repo_id, f.filename);
      if (!res.success) setNotice({ ok: false, text: res.message });
      kick();
    } catch (e) {
      setNotice({ ok: false, text: e instanceof ApiError ? e.message : t('lm.startError') });
    }
  };

  const run = async (work: () => Promise<{ success: boolean; message: string; model_id?: string }>) => {
    setBusy(true);
    setNotice(null);
    try {
      const res = await work();
      setNotice({ ok: res.success, text: res.message });
      if (res.success) {
        onHardwareChange();
        await refresh();
        if (res.model_id) update({ localModel: res.model_id });
      }
      return res.success;
    } catch (e) {
      setNotice({ ok: false, text: e instanceof ApiError ? e.message : t('lm.genericError') });
      return false;
    } finally {
      setBusy(false);
    }
  };

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) await run(() => api.uploadGGUF(file));
    if (fileRef.current) fileRef.current.value = '';
  };

  return (
    <div className="space-y-3">
      <input ref={fileRef} type="file" accept=".gguf" onChange={onFile} className="hidden" />

      <div className="overflow-hidden rounded-lg border">
        {state.status === 'loading' && (
          <div className="space-y-2 p-3" aria-busy="true" aria-label={t('lm.loadingInstalled')}>
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        )}

        {state.status === 'error' && (
          <div role="alert" className="flex items-center justify-between gap-3 p-4">
            <p className="text-sm text-critical-text">{state.message}</p>
            <Button variant="outline" size="sm" onClick={() => void refresh()}>
              <RotateCw className="size-3.5" /> {t('lm.retry')}
            </Button>
          </div>
        )}

        {state.status === 'ready' && models.length === 0 && running.length === 0 && (
          <div className="px-4 py-6">
            <p className="text-sm font-medium">{t('lm.noneTitle')}</p>
            <p className="mt-1 max-w-md text-sm text-muted-foreground">
              {rich('lm.noneBody', { ext: <code className="font-mono text-xs">.gguf</code> })}
            </p>
          </div>
        )}

        {state.status === 'ready' && models.length > 0 && (
          <div role="radiogroup" aria-label={t('lm.chatModel')} className="divide-y">
            {models.map((m) => (
              <InstalledRow key={m.id} model={m} active={m.id === activeId} onSelect={() => update({ localModel: m.id })} onDelete={() => setToDelete(m)} />
            ))}
          </div>
        )}

        {running.length > 0 && (
          <ul className="divide-y border-t">
            {running.map((j) => (
              <li key={j.job_id} className="px-3 py-2.5">
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <p className="flex min-w-0 items-center gap-1.5 text-sm">
                    <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" aria-hidden />
                    <span className="truncate font-medium">{j.filename}</span>
                  </p>
                  <Button variant="ghost" size="sm" className="h-6 shrink-0 px-2 text-xs" onClick={() => void api.hfCancel(j.job_id).then(kick)}>
                    {t('lm.cancel')}
                  </Button>
                </div>
                <Progress job={j} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" onClick={() => setBrowserOpen(true)}>
          {t('lm.browse')}
        </Button>
        <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={busy}>
          {t('lm.import')}
        </Button>
        <Button variant="outline" onClick={() => setLinkOpen(true)} disabled={busy}>
          {t('lm.linkPath')}
        </Button>
      </div>
      {failed.map((j) => (
        <p key={j.job_id} role="alert" className="text-xs text-critical-text">{j.filename}: {j.message}</p>
      ))}
      {notice && (
        <p role="status" className={cn('text-xs', notice.ok ? 'text-good-text' : 'text-critical-text')}>{notice.text}</p>
      )}

      <HuggingFaceBrowser open={browserOpen} onOpenChange={setBrowserOpen} jobs={jobs} hw={hw} onDownload={startDownload} />

      <Dialog open={linkOpen} onOpenChange={setLinkOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('lm.linkPathTitle')}</DialogTitle>
            <DialogDescription>{t('lm.linkPathDesc')}</DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <Input
              value={linkPath}
              onChange={(e) => setLinkPath(e.target.value)}
              placeholder={t('lm.linkPathPh')}
              className="font-mono text-xs"
              autoFocus
            />
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">{t('lm.cancel')}</Button>
            </DialogClose>
            <Button
              disabled={busy || !linkPath.trim()}
              onClick={async () => {
                const path = linkPath.trim();
                if (!path) return;
                setLinkOpen(false);
                setLinkPath('');
                await run(() => api.registerGGUF(path));
              }}
            >
              {t('lm.linkPathBtn')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={toDelete !== null} onOpenChange={(v) => !v && setToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('lm.deleteTitle', { name: toDelete ? modelLabel(toDelete) : '' })}</DialogTitle>
            <DialogDescription>
              {rich('lm.deleteBody', { folder: <code className="font-mono">models/</code>, size: toDelete?.size_gb ? `${toDelete.size_gb} GB` : t('lm.diskSpace') })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">{t('lm.keep')}</Button>
            </DialogClose>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={async () => {
                const m = toDelete;
                setToDelete(null);
                if (m) await run(async () => ({ ...(await api.deleteModel(m.id)), model_id: undefined }));
              }}
            >
              {t('lm.delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
