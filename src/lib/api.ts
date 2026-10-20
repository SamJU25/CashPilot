// Client for the FastAPI backend (api/routes/*). Every call carries this tab's session id, so uploads,
// chat and drafted actions stay in one backend session. Money stays a decimal string end to end.

import type { BalanceAt, CashAnalysis, LiveForecast, RecurringObligation, FinancingOption, ReceivablesAgeing, StagedActionIntent, UnderwritingDossier } from '@/lib/types';

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
const SESSION_KEY = 'cashpilot.session.v1';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export function sessionId(): string {
  try {
    let id = window.sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id = crypto.randomUUID();
      window.sessionStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch {
    return 'tab-' + Math.random().toString(36).slice(2);
  }
}

export function resetSession() {
  try {
    window.sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // Blocked storage: the next call makes a fresh id anyway.
  }
}

// The signed tenant token comes from our own Next.js route, which holds the enrollment key server side.
let tokenPromise: Promise<string | null> | null = null;
function tenantToken(): Promise<string | null> {
  tokenPromise ??= fetch('/api/session', { method: 'POST' })
    .then(async (r) => (r.ok ? ((await r.json()) as { token: string }).token : null))
    .catch(() => null);
  return tokenPromise;
}

// Uploads and lookups answer in seconds; a local model's first reply also loads its weights.
const TIMEOUT_MS = 60_000;
const CHAT_TIMEOUT_MS = 180_000;

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = TIMEOUT_MS): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('X-Session-ID', sessionId());
  const token = await tenantToken();
  if (token) headers.set('X-Tenant-Token', token);

  let res: Response;
  try {
    res = await fetch(API_URL + path, { ...init, headers, signal: AbortSignal.timeout(timeoutMs) });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'TimeoutError') throw new ApiError(0, 'TIMEOUT', `The CashPilot server did not answer within ${timeoutMs / 1000} seconds.`);
    throw new ApiError(0, 'UNREACHABLE', 'The CashPilot server did not answer. Check that it is running.');
  }
  if (res.status === 401) tokenPromise = null;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    // Routes answer either {error:{code,message}} or FastAPI's {detail}.
    // FastAPI validation errors arrive as a list; the first one's message is the readable part.
    const detail = typeof body?.detail === 'string' ? body.detail : Array.isArray(body?.detail) ? body.detail[0]?.msg : undefined;
    const err = body?.error ?? { code: `HTTP_${res.status}`, message: detail ?? res.statusText };
    throw new ApiError(res.status, err.code, err.message);
  }
  return body as T;
}

const form = (entries: [string, string | Blob, string?][]) => {
  const f = new FormData();
  for (const [k, v, name] of entries) (typeof v === 'string' ? f.append(k, v) : f.append(k, v, name));
  return f;
};

// services/calculations bucket names to the keys the Receivables screen and its strings use.
const BUCKET_KEYS: Record<string, string> = { CURRENT: 'current', '1_30': 'd1_30', '31_60': 'd31_60', '61_90': 'd61_90', OVER_90: 'd90_plus' };

export type AnalyzeResponse = CashAnalysis & { normalized_csv?: string | null };

export const api = {
  analyze: (files: File[], alertThresholdDays: number) =>
    request<AnalyzeResponse>('/api/v1/analyze', {
      method: 'POST',
      body: form([...files.map((f) => ['files', f, f.name] as [string, Blob, string]), ['alert_threshold_days', String(alertThresholdDays)]]),
    }),
  adjustCash: (body: {
    current_balance: string;
    adjustment_type: 'INFLOW' | 'OUTFLOW' | 'SET_BALANCE';
    amount: string;
    description?: string;
    daily_burn?: string;
    currency?: string;
    effective_date?: string;
    alert_threshold_days?: number;
    account_id?: string;
    accounts?: { account_id: string; balance: string }[];
  }) =>
    request<AnalyzeResponse>('/api/v1/analyze/adjust', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  summaryAnalyze: (body: {
    current_balance: string;
    monthly_burn?: string;
    daily_burn?: string;
    monthly_inflow?: string;
    currency?: string;
    as_of_date?: string;
    alert_threshold_days?: number;
    account_name?: string;
  }) =>
    request<AnalyzeResponse>('/api/v1/analyze/summary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  scenario: (body: {
    current_balance: string;
    average_daily_burn: string;
    anchor_date: string;
    obligations: RecurringObligation[];
    variable_cut_pct?: string;
    extra_monthly_payroll?: string;
    one_off_inflows?: { date: string; amount: string }[];
  }) =>
    request<{ forecast: LiveForecast; projection: BalanceAt[] }>('/api/v1/analyze/scenario', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  underwrite: (csv: Blob, name: string) =>
    request<{ dossier: UnderwritingDossier; matched_options: FinancingOption[] }>('/api/v1/underwrite', { method: 'POST', body: form([['file', csv, name]]) }),
  invoices: async (file: File) => {
    const r = await request<ReceivablesAgeing>('/api/v1/analyze/invoices', { method: 'POST', body: form([['file', file, file.name]]) });
    return { ...r, buckets: Object.fromEntries(Object.entries(r.buckets).map(([k, v]) => [BUCKET_KEYS[k] ?? k, v])) };
  },
  chat: (body: ChatRequest) =>
    request<ChatResponse>('/api/v1/agent/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, session_id: sessionId() }) }, CHAT_TIMEOUT_MS),
  actions: () => request<StagedActionIntent[]>('/api/v1/actions'),
  prepare: (id: string) => request<StagedActionIntent>(`/api/v1/actions/${encodeURIComponent(id)}/prepare`, { method: 'POST' }),
  reject: (id: string) => request<StagedActionIntent>(`/api/v1/actions/${encodeURIComponent(id)}/reject`, { method: 'POST' }),
  testConnection: (config: NonNullable<ChatRequest['llm_config']>) =>
    request<{ success: boolean; message: string; provider: string; model_name?: string | null; latency_ms?: number | null }>('/api/v1/agent/test-connection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    }, CHAT_TIMEOUT_MS),
  health: () => request<{ status: string; version: string }>('/api/v1/health', {}, 5_000),
  clearSession: () => request<{ cleared: boolean }>(`/api/v1/agent/session/${encodeURIComponent(sessionId())}`, { method: 'DELETE' }),
  fetchModels: (provider: string, apiKey?: string, baseUrl?: string) =>
    request<{ success: boolean; provider: string; models: { id: string; name: string }[]; message?: string }>('/api/v1/agent/fetch-models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, api_key: apiKey, base_url: baseUrl }),
    }, 15_000),
  downloadModel: (modelName: string) =>
    request<{ success: boolean; model_name: string; message: string; downloaded_path?: string | null; size_mb?: number | null }>('/api/v1/agent/download-model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_name: modelName }),
    }, CHAT_TIMEOUT_MS),
  deleteModel: (modelName: string) =>
    request<{ success: boolean; model_name: string; message: string; freed_mb?: number }>('/api/v1/agent/delete-model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_name: modelName }),
    }, 30_000),
};

export interface ChatRequest {
  message: string;
  history: { role: 'user' | 'agent'; text: string }[];
  alert_threshold_days: number;
  currency?: string;
  language?: string;
  csv_content?: string;
  llm_config?: { provider: string; api_key?: string; base_url?: string; model_name?: string };
}

export interface ChatResponse {
  reply: string;
  intent_detected: string;
  staged_action?: { intent_id: string; action_type: string; amount_cents: number; target_identifier: string; status: string } | null;
  proposed_entry?: ProposedEntry | null;
  session_id?: string | null;
}

/** A cash entry the backend read from a chat message; recorded only when the owner confirms the card. */
export interface ProposedEntry {
  adjustment_type: 'INFLOW' | 'OUTFLOW';
  amount: string;
  date: string;
  description: string;
  account_hint?: string | null;
}

/** Frontend provider ids to services/agent/llm_bridge.py ids. */
export function llmConfig(provider: string, keys: Record<string, string>, urls: Record<string, string>, defaultUrl: string, selectedModel?: string): ChatRequest['llm_config'] {
  const key = keys[provider]?.trim() || undefined;
  const url = urls[provider]?.trim() || defaultUrl || undefined;
  if (provider === 'local') return { provider: 'local', model_name: selectedModel || 'qwen2.5-3b-instruct' };
  // Ollama speaks the OpenAI protocol under /v1.
  if (provider === 'ollama') return { provider: 'custom', base_url: `${(url ?? 'http://localhost:11434').replace(/\/$/, '')}/v1`, model_name: selectedModel };
  if (provider === 'claude') return { provider: 'anthropic', api_key: key, model_name: selectedModel };
  if (provider === 'custom') return { provider: 'custom', api_key: key, base_url: url, model_name: selectedModel };
  return { provider, api_key: key, model_name: selectedModel };
}
