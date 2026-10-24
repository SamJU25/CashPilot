import type { TraceEvent } from '@/lib/runs';
import { DEFAULT_PROVIDER_MODELS } from '@/lib/providers';
// Client for the FastAPI backend (api/routes/*). Every call carries this tab's session id, so uploads,
// chat and drafted actions stay in one backend session. Money stays a decimal string end to end.

import type { BalanceAt, CashAnalysis, LiveForecast, RecurringObligation, FinancingOption, ReceivablesAgeing, StagedActionIntent, StagingRequest, UnderwritingDossier } from '@/lib/types';
export type { CashAnalysis };

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
async function fetchTenantToken(): Promise<string | null> {
  try {
    const r = await fetch('/api/session', { method: 'POST' });
    if (r.ok) {
      const data = (await r.json()) as { token: string };
      if (data.token) return data.token;
    }
  } catch {
    // In desktop export there is no Next.js server; fall through to local FastAPI
  }

  // In Desktop / local FastAPI: /api/v1/auth/local-session
  // If the backend is cold-starting, retry with backoff over ~3.5s before giving up
  const retryDelays = [200, 400, 800, 1200];
  for (let attempt = 0; attempt <= retryDelays.length; attempt++) {
    try {
      const res = await fetch(`${API_URL}/api/v1/auth/local-session`, { method: 'POST' });
      if (res.ok) {
        const data = (await res.json()) as { access_token: string };
        return data.access_token;
      }
    } catch {
      // Backend is still initializing
    }
    if (attempt < retryDelays.length) {
      await new Promise((resolve) => setTimeout(resolve, retryDelays[attempt]));
    }
  }
  return null;
}

function tenantToken(): Promise<string | null> {
  if (!tokenPromise) {
    tokenPromise = fetchTenantToken().then((tok) => {
      if (!tok) tokenPromise = null;
      return tok;
    });
  }
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

  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  let signal: AbortSignal;
  if (init.signal) {
    if (typeof AbortSignal.any === 'function') {
      signal = AbortSignal.any([init.signal, timeoutSignal]);
    } else {
      const controller = new AbortController();
      init.signal.addEventListener('abort', () => controller.abort(init.signal?.reason), { once: true });
      timeoutSignal.addEventListener('abort', () => controller.abort(timeoutSignal.reason), { once: true });
      signal = controller.signal;
    }
  } else {
    signal = timeoutSignal;
  }

  let res: Response;
  const isRead = !init.method || init.method.toUpperCase() === 'GET';
  const delays = [300, 600, 1000, 1500];
  let attempt = 0;
  while (true) {
    try {
      res = await fetch(API_URL + path, { ...init, headers, signal });
      break;
    } catch (e) {
      if (init.signal?.aborted || (e instanceof DOMException && e.name === 'AbortError')) throw e;
      if (isRead && attempt < delays.length) {
        await new Promise((r) => setTimeout(r, delays[attempt++]));
        continue;
      }
      if (e instanceof DOMException && e.name === 'TimeoutError') {
        throw new ApiError(0, 'TIMEOUT', `The CashPilot server did not answer within ${timeoutMs / 1000} seconds.`);
      }
      throw new ApiError(0, 'UNREACHABLE', 'The CashPilot server did not answer. Check that it is running.');
    }
  }

  if (res.status === 401) {
    tokenPromise = null;
    const freshToken = await tenantToken();
    if (freshToken && freshToken !== token) {
      headers.set('X-Tenant-Token', freshToken);
      res = await fetch(API_URL + path, { ...init, headers, signal });
    }
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    // Routes answer either {error:{code,message}} or FastAPI's {detail}.
    // FastAPI validation errors arrive as a list; the first one's message is the readable part.
    const detail = typeof body?.detail === 'string' ? body.detail : Array.isArray(body?.detail) ? body.detail[0]?.msg : undefined;
    const err = body?.error ?? (body?.detail?.code ? body.detail : { code: `HTTP_${res.status}`, message: detail ?? res.statusText });
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

// services/mail: the read-only bank alerts mailbox.
export interface MailAlert {
  id: string;
  bank: string;
  bank_domain: string;
  account_tail: string;
  currency: string;
  direction: 'IN' | 'OUT';
  amount: string;
  balance_after: string | null;
  occurred_on: string;
  counterparty: string | null;
  verified: boolean;
  review: 'no_account' | 'no_direction' | 'unverified_sender' | 'unlisted_bank' | null;
  resolved: 'accept' | 'dismiss' | null;
  status: 'ready' | 'waiting' | 'ignored' | 'review' | 'dismissed';
  /** Balance arithmetic did not follow from the previous alert: this much is unexplained. */
  gap: string | null;
  transfer_with: string | null;
}
export interface MailAccount {
  key: string;
  bank: string;
  bank_domain: string;
  tail: string;
  currency: string;
  status: 'pending' | 'use' | 'ignore';
  target: string | null;
  balance: string | null;
  alerts: number;
  last_seen?: string;
}
export interface MailState {
  connection: { address: string; host: string; port: number; username: string; name: string; oauth: 'google' | 'microsoft' | null; verifies_sender: boolean; last_sync: string | null; last_error: string | null } | null;
  banks: Record<string, { name: string; currency: string }>;
  trusted: string[];
  accounts: MailAccount[];
  alerts: MailAlert[];
  result?: { read: number; added: number };
}
/** IMAP settings found from an address the way Thunderbird finds them (services/mail/discover.py). */
export interface MailSettings {
  host: string;
  port: number;
  username: string;
  source: 'provider' | 'ispdb' | 'mx' | 'guess';
  name: string;
  /** The provider only allows sign-in through its own window; an app password will not work. */
  oauth_only: boolean;
  verifies_sender: boolean;
  secret_kind: 'app_password' | 'auth_code' | 'password';
  /** Browser sign-in is set up on this computer for this provider. */
  oauth: 'google' | 'microsoft' | null;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const mailApi = {
  banks: () => request<{ banks: { domain: string; name: string; currency: string }[] }>('/api/v1/mail/banks'),
  discover: (address: string) => request<{ settings: MailSettings | null }>('/api/v1/mail/discover', json('POST', { address })),
  state: () => request<MailState>('/api/v1/mail/state'),
  connect: (body: { address: string; secret: string; host: string; port: number; username: string; name: string }) => request<MailState>('/api/v1/mail/connect', json('POST', body)),
  disconnect: () => request<MailState>('/api/v1/mail/connect', { method: 'DELETE' }),
  sync: () => request<MailState>('/api/v1/mail/sync', { method: 'POST' }),
  oauthStart: (body: { address: string; host: string; username: string; name: string; return_to?: string }) => request<{ url: string }>('/api/v1/mail/oauth/start', json('POST', body)),
  decideAccount: (key: string, status: MailAccount['status'], target?: string) =>
    request<MailState>(`/api/v1/mail/accounts/${encodeURIComponent(key)}`, json('PUT', { status, target })),
  decideAlert: (id: string, action: 'accept' | 'dismiss' | 'trust') => request<MailState>(`/api/v1/mail/alerts/${encodeURIComponent(id)}`, json('PUT', { action })),
  addBank: (body: { domain: string; name: string; currency: string }) => request<MailState>('/api/v1/mail/banks', json('POST', body)),
  removeBank: (domain: string) => request<MailState>(`/api/v1/mail/banks/${encodeURIComponent(domain)}`, { method: 'DELETE' }),
};

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
  chat: (body: ChatRequest, signal?: AbortSignal) =>
    request<ChatResponse>('/api/v1/agent/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, session_id: sessionId() }), signal }, CHAT_TIMEOUT_MS),
  actions: () => request<StagedActionIntent[]>('/api/v1/actions'),
  stageAction: (body: StagingRequest) => request<StagedActionIntent>('/api/v1/actions/stage', json('POST', body)),
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
  hardware: () => request<Hardware>('/api/v1/agent/hardware', {}, 10_000),
  hfSearch: (q: string, sort: string, cursor?: string | null) =>
    request<{ success: boolean; models: HFRepo[]; next_cursor?: string | null; message?: string | null }>(
      `/api/v1/agent/hf/search?q=${encodeURIComponent(q)}&sort=${sort}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`,
      {},
      45_000,
    ),
  hfFiles: (repoId: string) =>
    request<{ success: boolean; repo_id: string; files: HFFile[]; message?: string | null }>(`/api/v1/agent/hf/files?repo_id=${encodeURIComponent(repoId)}`, {}, 20_000),
  hfDownload: (repoId: string, filename: string) =>
    request<{ success: boolean; message: string; job: HFDownload | null }>('/api/v1/agent/hf/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_id: repoId, filename }),
    }),
  hfDownloads: () => request<HFDownload[]>('/api/v1/agent/hf/downloads', {}, 10_000),
  hfCancel: (jobId: string) => request<{ cancelled: boolean }>(`/api/v1/agent/hf/downloads/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' }),
  fetchModels: (provider: string, apiKey?: string, baseUrl?: string) =>
    request<{ success: boolean; provider: string; models: LocalModel[]; message?: string }>('/api/v1/agent/fetch-models', {
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
  uploadGGUF: (file: File) =>
    request<{ success: boolean; model_id: string; model_name: string; message: string; size_gb?: number }>('/api/v1/agent/upload-gguf', {
      method: 'POST',
      body: form([['file', file, file.name]]),
    }, 120_000),
  registerGGUF: (filePath: string) =>
    request<{ success: boolean; model_id: string; model_name: string; message: string; size_gb?: number }>('/api/v1/agent/register-gguf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath }),
    }, 30_000),
  sentinelHeartbeat: () => request<SentinelTelemetry>('/api/v1/sentinel/heartbeat', {}, 5_000),
  sentinelEvaluate: () => request<SentinelEvaluationResult>('/api/v1/sentinel/evaluate', { method: 'POST' }, 15_000),
};

/** A model from fetch-models; `installed`, `repo_id` and `quant` are set for local GGUF models only. */
export interface LocalModel {
  id: string;
  name: string;
  tool_calling?: string | null;
  size_gb?: number | null;
  tier?: string | null;
  installed?: boolean | null;
  repo_id?: string | null;
  quant?: string | null;
}

/** Live memory of the machine running the backend; null when it cannot be read. */
export interface Hardware {
  ram_total_gb: number | null;
  ram_available_gb: number | null;
  gpu_name: string | null;
  vram_total_gb: number | null;
  vram_free_gb: number | null;
}

export interface HFRepo {
  repo_id: string;
  author: string;
  name: string;
  downloads: number;
  likes: number;
  last_modified: string | null;
  parameters: number | null;
  context_length: number | null;
  architecture: string | null;
  tool_calling: string | null;
}

export interface HFFile {
  filename: string;
  size_bytes: number | null;
  quant: string | null;
  installed: boolean;
  recommended: boolean;
}

export interface HFDownload {
  job_id: string;
  repo_id: string;
  filename: string;
  model_id: string;
  status: 'queued' | 'downloading' | 'completed' | 'failed' | 'cancelled';
  downloaded_bytes: number;
  total_bytes: number | null;
  message: string | null;
}

export interface ChatRequest {
  message: string;
  history: { role: 'user' | 'agent'; text: string }[];
  alert_threshold_days: number;
  currency?: string;
  language?: string;
  has_statement?: boolean;
  csv_content?: string;
  llm_config?: { provider: string; api_key?: string; base_url?: string; model_name?: string };
}

export interface ChatResponse {
  reply: string;
  intent_detected: string;
  staged_action?: { intent_id: string; action_type: string; amount_cents: number; target_identifier: string; status: string } | null;
  proposed_entry?: ProposedEntry | null;
  session_id?: string | null;
  /** What ran to produce the answer; drawn on the workstation page. */
  trace?: TraceEvent[];
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
  const model = selectedModel?.trim() || DEFAULT_PROVIDER_MODELS[provider] || undefined;
  // No model picked: the backend answers with how to install one instead of guessing a file.
  if (provider === 'local') return { provider: 'local', model_name: model || undefined };
  // Ollama runs locally on :11434 with an OpenAI-compatible /v1 interface.
  if (provider === 'ollama') return { provider: 'ollama', base_url: `${(url ?? 'http://localhost:11434').replace(/\/$/, '')}/v1`, model_name: model || 'llama3.2' };
  if (provider === 'claude') return { provider: 'anthropic', api_key: key, model_name: model };
  if (provider === 'custom') return { provider: 'custom', api_key: key, base_url: url, model_name: model };
  return { provider, api_key: key, base_url: url, model_name: model };
}

export interface SentinelTelemetry {
  daemon_status: 'RUNNING' | 'STOPPED';
  started_at: string | null;
  last_sweep_at: string | null;
  cycle_count: number;
  interval_seconds: number;
  last_sweep_summary: {
    status: string;
    cycle: number;
    tenants_audited: number;
    deficits_detected: number;
    actions_staged: number;
    timestamp: string;
    error?: string;
  };
}

export interface SentinelEvaluationResult {
  status: string;
  cycle: number;
  tenants_audited: number;
  deficits_detected: number;
  actions_staged: number;
  timestamp: string;
  error?: string | null;
}
