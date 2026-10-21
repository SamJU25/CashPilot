// The traces of recent Assistant answers, kept in this tab for the workstation page.
// Tab-scoped like the rest of the owner's figures; nothing here leaves the browser.

export type TraceKind = 'agent' | 'tool' | 'decision' | 'card';

/** One step of a run as the backend recorded it: names, outcomes and timings only. */
export interface TraceEvent {
  kind: TraceKind;
  name: string;
  agent: string;
  start_ms: number;
  duration_ms: number;
  detail: Record<string, string>;
}

export interface RecordedRun {
  id: string;
  question: string;
  intent: string;
  at: string;
  trace: TraceEvent[];
}

const KEY = 'cashpilot.runs.v1';
const MAX_RUNS = 12;
export const RUNS_EVENT = 'cashpilot:runs';

export function readRuns(): RecordedRun[] {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as RecordedRun[]) : [];
  } catch {
    return [];
  }
}

export function saveRun(run: Omit<RecordedRun, 'id' | 'at'>): RecordedRun | null {
  if (!run.trace?.length) return null;
  const t0 = run.trace[0].start_ms;
  // Times are kept relative to the run's first step, so every run starts at zero.
  const saved: RecordedRun = {
    ...run,
    id: crypto.randomUUID(),
    at: new Date().toISOString(),
    trace: run.trace.map((e) => ({ ...e, start_ms: Math.round((e.start_ms - t0) * 100) / 100 })),
  };
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify([saved, ...readRuns()].slice(0, MAX_RUNS)));
    window.dispatchEvent(new CustomEvent(RUNS_EVENT));
  } catch {
    // Blocked storage: the run is still drawn if the page is open, but is not kept.
  }
  return saved;
}
