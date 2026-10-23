'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { RotateCcw, Workflow } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/common/bits';
import { Blueprint } from '@/components/workstation/blueprint';
import { ENGINE_LABEL, formatMs, humanize, stepsOf, summary, type Step } from '@/components/workstation/model';
import { SAMPLE_RUNS } from '@/lib/mock/traces';
import { RUNS_EVENT, readRuns, type RecordedRun } from '@/lib/runs';
import { formatDateTime } from '@/lib/format';
import { useT, type Key } from '@/lib/i18n';
import { useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';

function Legend() {
  const { t } = useT();
  const item = (shape: React.ReactNode, label: Key) => (
    <span className="inline-flex items-center gap-2">
      <svg width={18} height={18} viewBox="-9 -9 18 18" aria-hidden>
        {shape}
      </svg>
      {t(label)}
    </span>
  );
  const stroke = 'rgb(var(--primary))';
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted-foreground">
      {item(<rect x={-5} y={-5} width={10} height={10} transform="rotate(45)" fill="none" stroke={stroke} strokeWidth={1.5} />, 'wk.lg.decision')}
      {item(<rect x={-5} y={-5} width={10} height={10} fill="none" stroke={stroke} strokeWidth={1.5} />, 'wk.lg.tool')}
      {item(<rect x={-6} y={-4} width={12} height={8} rx={1.5} fill="none" stroke={stroke} strokeWidth={1.25} strokeDasharray="2.5 1.5" />, 'wk.lg.card')}
      {item(<circle r={5} fill="none" stroke={stroke} strokeWidth={1.5} />, 'wk.lg.handoff')}
      {item(<path d="M -8 0 H 8" stroke={stroke} strokeWidth={1.6} />, 'wk.lg.path')}
      {item(<path d="M -8 0 H 8" stroke="rgb(var(--s4))" strokeWidth={1.2} strokeDasharray="5 3" />, 'wk.lg.read')}
      {item(<path d="M -8 0 H 8" stroke="rgb(var(--ink-2))" strokeWidth={1.2} strokeDasharray="2 3" />, 'wk.lg.refer')}
    </div>
  );
}

/** Everything the trace knows about one step, in words first and identifiers second. */
function Detail({ step }: { step: Step }) {
  const { t } = useT();
  const rows: [Key, React.ReactNode][] = [];
  if (step.kind === 'decision') {
    const engine = ENGINE_LABEL(step.detail.engine);
    const conf = Number(step.detail.confidence ?? 0);
    const bar = Number(step.detail.threshold ?? 0);
    rows.push(['wk.dt.outcome', humanize(step.detail.choice ?? '')]);
    rows.push(['wk.dt.engine', <span key="e">{engine ? t(engine as Key) : ''} <span className="font-mono text-xs text-muted-foreground">{step.detail.engine}</span></span>]);
    if (step.detail.rule) rows.push(['wk.dt.rule', <span key="r" className="font-mono text-xs">{step.detail.rule}</span>]);
    rows.push([
      'wk.dt.confidence',
      <span key="c" className="flex items-center gap-3">
        <span className="relative h-1.5 w-32 rounded-full bg-muted" aria-hidden>
          <span className={cn('absolute inset-y-0 left-0 rounded-full', conf >= bar ? 'bg-primary' : 'bg-warning')} style={{ width: `${Math.min(100, conf * 100)}%` }} />
          <span className="absolute -inset-y-1 w-px bg-foreground" style={{ left: `${bar * 100}%` }} />
        </span>
        <span className="figures">{t('wk.dt.confValue', { c: conf.toFixed(2), b: bar.toFixed(2) })}</span>
      </span>,
    ]);
    if (step.detail.fallback === 'true') rows.push(['wk.dt.fallback', t('wk.dt.fallbackYes')]);
    if (step.count > 1) rows.push(['wk.dt.repeated', t('wk.dt.times', { n: step.count })]);
  } else if (step.kind === 'tool') {
    rows.push(['wk.dt.function', <span key="f" className="font-mono text-xs">{step.name}()</span>]);
    rows.push(['wk.dt.result', step.detail.ok === 'true' ? t('wk.dt.ok') : t('wk.dt.failed')]);
  } else if (step.kind === 'card') {
    rows.push(['wk.dt.file', <span key="f" className="font-mono text-xs">knowledge/cards/{step.detail.file}</span>]);
    rows.push(['wk.dt.relevance', step.detail.score]);
  }
  rows.push(['wk.dt.time', <span key="t" className="figures">{formatMs(step.duration)}</span>]);

  return (
    <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[9rem_1fr]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{t(k)}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function RunList({ title, runs, current, onPick }: { title: string; runs: RecordedRun[]; current: string; onPick: (id: string) => void }) {
  const { t } = useT();
  if (runs.length === 0) return null;
  return (
    <div className="min-w-0">
      <p className="pb-2 text-xs font-medium text-muted-foreground">{title}</p>
      <ul className="flex gap-2 overflow-x-auto pb-1">
        {runs.map((r) => {
          const s = summary(r.trace);
          return (
            <li key={r.id} className="w-60 shrink-0">
              <button
                type="button"
                onClick={() => onPick(r.id)}
                aria-current={r.id === current}
                className={cn('h-full w-full rounded-lg border px-3 py-2.5 text-left transition-colors', r.id === current ? 'border-primary bg-accent text-accent-foreground' : 'bg-card hover:bg-muted')}
              >
                <span className="line-clamp-2 text-sm font-medium">{r.question}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">{t('wk.runMeta', { n: r.trace.length, ms: formatMs(s.ms) })}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function WorkstationPage() {
  const { t } = useT();
  const { source, loadSample } = useWorkspace();
  const isDemo = source === 'sample';
  const [own, setOwn] = useState<RecordedRun[]>([]);
  const [current, setCurrent] = useState<string>('');
  const [selected, setSelected] = useState<string | null>(null);
  const [playKey, setPlayKey] = useState(0);

  useEffect(() => {
    const load = () => {
      const runs = readRuns();
      setOwn(runs);
      if (runs[0]) {
        setCurrent(runs[0].id);
      } else if (isDemo) {
        setCurrent(SAMPLE_RUNS[0].id);
      }
    };
    load();
    window.addEventListener(RUNS_EVENT, load);
    return () => window.removeEventListener(RUNS_EVENT, load);
  }, [isDemo]);

  // When demo mode is active, include sample runs. Otherwise, only user runs are shown.
  const availableRuns = useMemo(() => {
    return isDemo ? [...own, ...SAMPLE_RUNS] : own;
  }, [isDemo, own]);

  const run = availableRuns.find((r) => r.id === current) ?? availableRuns[0] ?? null;
  const steps = useMemo(() => (run ? stepsOf(run.trace) : []), [run]);
  const stats = useMemo(() => (run ? summary(run.trace) : null), [run]);
  const step = steps.find((s) => s.key === selected) ?? null;
  const pick = (id: string) => {
    setCurrent(id);
    setSelected(null);
    setPlayKey((k) => k + 1);
  };

  // If not in demo mode and no live user runs exist, display a clean empty guidance state
  if (!isDemo && own.length === 0) {
    return (
      <div>
        <PageHeader title={t('wk.title')} description={t('wk.desc')} />
        <div className="mt-8 rounded-xl border border-dashed bg-card/50 px-6 py-16 text-center">
          <Workflow className="mx-auto size-12 text-muted-foreground/50" aria-hidden />
          <h2 className="mt-4 font-display text-lg font-semibold">{t('wk.emptyTitle')}</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            {t('wk.emptyBody')}
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <Button asChild>
              <Link href="/assistant">{t('nav.assistant')}</Link>
            </Button>
            <Button variant="outline" onClick={() => loadSample()}>
              {t('ov.welcome.sample')}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (!run || !stats) return null;

  return (
    <div>
      <PageHeader title={t('wk.title')} description={t('wk.desc')} />

      <div className="space-y-4">
        <aside className="space-y-3">
          <RunList title={t('wk.yours')} runs={own} current={run.id} onPick={pick} />
          {isDemo && <RunList title={t('wk.examples')} runs={SAMPLE_RUNS} current={run.id} onPick={pick} />}
          {own.length === 0 && isDemo && <p className="text-xs text-muted-foreground">{t('wk.askHint')}</p>}
        </aside>

        <section className="min-w-0 overflow-hidden rounded-xl border bg-card">
          <header className="flex flex-wrap items-start justify-between gap-4 border-b p-5">
            <div className="min-w-0">
              <p className="font-mono text-xs text-muted-foreground">
                {t('wk.fig', { n: 1 })}
                {!run.id.startsWith('sample-') && <span className="ml-2">{formatDateTime(run.at)}</span>}
              </p>
              <h2 className="mt-1 font-display text-xl font-semibold tracking-tight">“{run.question}”</h2>
              <p className="mt-1 text-sm text-muted-foreground">{t('wk.answeredAs', { intent: humanize(run.intent) })}</p>
            </div>
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setPlayKey((k) => k + 1)}>
              <RotateCcw className="size-3.5" aria-hidden />
              {t('wk.replay')}
            </Button>
          </header>

          <dl className="grid grid-cols-2 border-b sm:grid-cols-5 sm:divide-x">
            {(
              [
                ['wk.st.decisions', stats.decisions],
                ['wk.st.tools', stats.tools],
                ['wk.st.cards', stats.cards],
                ['wk.st.agents', stats.agents],
                ['wk.st.time', formatMs(stats.ms)],
              ] as [Key, string | number][]
            ).map(([k, v]) => (
              <div key={k} className="px-5 py-3">
                <dt className="text-xs text-muted-foreground">{t(k)}</dt>
                <dd className="figures font-display text-xl font-semibold">{v}</dd>
              </div>
            ))}
          </dl>

          <div className="border-b px-5 py-3">
            <Legend />
          </div>

          <div className="overflow-x-auto">
            <Blueprint run={run} selected={selected} onSelect={(k) => setSelected((s) => (s === k ? null : k))} playKey={playKey} />
          </div>

          <div className="border-t p-5">
            {step ? <Detail step={step} /> : <p className="text-sm text-muted-foreground">{t('wk.pickStep')}</p>}
            <p className="mt-4 text-xs text-muted-foreground">{t('wk.honest')}</p>
          </div>
        </section>
      </div>
    </div>
  );
}
