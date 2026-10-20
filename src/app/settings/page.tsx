'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { AlertTriangle, Check, ChevronsUpDown, Globe, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
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
import { PageHeader } from '@/components/common/bits';
import { BlueprintMark, CashPilotMark, Wordmark } from '@/components/shell/brand';
import { LANGUAGES, useT, type Lang } from '@/lib/i18n';
import { fade } from '@/lib/motion';
import { DEFAULT_PROVIDER_MODELS, PROVIDERS, providerName } from '@/lib/providers';
import { ApiError, api, llmConfig } from '@/lib/api';
import { cn } from '@/lib/utils';
import { useWorkspace, type Theme } from '@/lib/workspace';
import { WORLD_CURRENCIES } from '@/lib/currencies';

// Stays in English in every language. Illustrative; the tags are the ones services/agent/llm_bridge.py
// (mask_pii) and services/agent/name_masking.py write before text goes to a cloud provider.
const REDACTED_EXAMPLE = `Question: Is [PARTY_1] paying us late?
Context (calculated, not estimated):
  accounts: Operating [REDACTED_ACCOUNT], Payroll [REDACTED_ACCOUNT]
  current_balance: 29922.08 USD
  first_negative_day: 2026-10-28, trigger PAYROLL
  shortfall: 5866.76 USD
  largest_customer: [PARTY_1] ([REDACTED_EMAIL]), 47 days overdue
Masked before sending: account numbers, IBANs, tax IDs, emails, phone numbers, names.
The reply you see has the real names put back.`;

function Row({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-4 py-6 md:grid-cols-[minmax(0,300px)_1fr] md:gap-10">
      <div>
        <h3 className="text-sm font-medium">{title}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="pt-6">
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="divide-y">{children}</div>
    </section>
  );
}

function LanguageCombobox({ value, onChange }: { value: Lang; onChange: (lang: Lang) => void }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');

  const current = LANGUAGES.find((l) => l.id === value) ?? LANGUAGES[0];

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    if (!q) return LANGUAGES;
    return LANGUAGES.filter(
      (l) =>
        l.id.toLowerCase().includes(q) ||
        l.label.toLowerCase().includes(q) ||
        ('englishName' in l && (l as { englishName?: string }).englishName?.toLowerCase().includes(q))
    );
  }, [search]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="h-9 w-full max-w-sm justify-between border-input bg-background font-normal text-foreground shadow-sm hover:bg-accent/40 hover:text-accent-foreground focus-visible:ring-1 focus-visible:ring-ring"
        >
          <span className="truncate flex items-center gap-2">
            <Globe className="size-4 text-muted-foreground shrink-0" />
            <span className="font-semibold text-foreground">{current.label}</span>
            <span className="font-mono text-xs uppercase text-muted-foreground">({current.id})</span>
            {current.englishName && current.englishName !== current.label && (
              <span className="truncate text-ink-2">— {current.englishName}</span>
            )}
          </span>
          <ChevronsUpDown className="ml-2 size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(360px,calc(100vw-2rem))] p-2 bg-popover text-popover-foreground border-border shadow-md rounded-md" align="start">
        <div className="relative mb-2">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input
            placeholder={t('set.searchLang')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 pl-8 text-base sm:text-xs bg-muted/40 border-input placeholder:text-muted-foreground text-foreground focus-visible:ring-1 focus-visible:ring-ring"
            autoFocus
          />
        </div>
        <ScrollArea className="max-h-64 overflow-y-auto pr-1">
          {filtered.length === 0 ? (
            <p className="py-6 text-center text-xs text-muted-foreground">
              {t('set.noMatch', { q: search })}
            </p>
          ) : (
            <div className="space-y-0.5">
              {filtered.map((l) => {
                const selected = l.id === value;
                return (
                  <button
                    key={l.id}
                    type="button"
                    onClick={() => {
                      onChange(l.id as Lang);
                      setOpen(false);
                      setSearch('');
                    }}
                    className={cn(
                      'flex w-full items-center justify-between rounded px-2.5 py-1.5 text-left text-xs transition-colors',
                      'hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground focus:outline-none',
                      selected
                        ? 'bg-accent font-medium text-accent-foreground'
                        : 'text-foreground'
                    )}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-12 font-mono font-semibold text-muted-foreground uppercase shrink-0">{l.id}</span>
                      <span className="font-medium text-foreground shrink-0">{l.label}</span>
                      {l.englishName && l.englishName !== l.label && (
                        <span className="truncate text-ink-2">({l.englishName})</span>
                      )}
                    </div>
                    {selected && <Check className="ml-2 size-3.5 text-primary shrink-0" />}
                  </button>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}

function CurrencyCombobox({ value, onChange }: { value: string; onChange: (code: string) => void }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');

  const current = WORLD_CURRENCIES.find((c) => c.code === value) ?? WORLD_CURRENCIES[0];

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    if (!q) return WORLD_CURRENCIES;
    return WORLD_CURRENCIES.filter(
      (c) =>
        c.code.toLowerCase().includes(q) ||
        c.name.toLowerCase().includes(q) ||
        c.symbol.toLowerCase().includes(q) ||
        c.region.toLowerCase().includes(q)
    );
  }, [search]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="h-9 w-full max-w-sm justify-between border-input bg-background font-normal text-foreground shadow-sm hover:bg-accent/40 hover:text-accent-foreground focus-visible:ring-1 focus-visible:ring-ring"
        >
          <span className="truncate flex items-center gap-1.5">
            <span className="font-semibold text-foreground">{current.code}</span>{' '}
            <span className="text-muted-foreground">({current.symbol})</span>
            <span className="text-ink-2">— {current.name}</span>
          </span>
          <ChevronsUpDown className="ml-2 size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(360px,calc(100vw-2rem))] p-2 bg-popover text-popover-foreground border-border shadow-md rounded-md" align="start">
        <div className="relative mb-2">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input
            placeholder={t('set.searchCur')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 pl-8 text-base sm:text-xs bg-muted/40 border-input placeholder:text-muted-foreground text-foreground focus-visible:ring-1 focus-visible:ring-ring"
            autoFocus
          />
        </div>
        <ScrollArea className="max-h-64 overflow-y-auto pr-1">
          {filtered.length === 0 ? (
            <p className="py-6 text-center text-xs text-muted-foreground">
              {t('set.noMatch', { q: search })}
            </p>
          ) : (
            <div className="space-y-0.5">
              {filtered.map((c) => {
                const selected = c.code === value;
                return (
                  <button
                    key={c.code}
                    type="button"
                    onClick={() => {
                      onChange(c.code);
                      setOpen(false);
                      setSearch('');
                    }}
                    className={cn(
                      'flex w-full items-center justify-between rounded px-2.5 py-1.5 text-left text-xs transition-colors',
                      'hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground focus:outline-none',
                      selected
                        ? 'bg-accent font-medium text-accent-foreground'
                        : 'text-foreground'
                    )}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-9 font-mono font-semibold text-foreground shrink-0">{c.code}</span>
                      <span className="w-6 text-center font-medium text-foreground shrink-0">{c.symbol}</span>
                      <span className="truncate text-ink-2">{c.name}</span>
                    </div>
                    {selected && <Check className="ml-2 size-3.5 text-primary shrink-0" />}
                  </button>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}

export default function SettingsPage() {
  const ws = useWorkspace();
  const { t } = useT();
  const provider = PROVIDERS.find((p) => p.id === ws.provider) ?? PROVIDERS[0];
  const baseUrl = ws.providerUrls[provider.id] ?? provider.baseUrl;
  const apiKey = ws.providerKeys[provider.id] ?? '';
  const setBaseUrl = (v: string) => ws.update({ providerUrls: { ...ws.providerUrls, [provider.id]: v } });
  const setApiKey = (v: string) => ws.update({ providerKeys: { ...ws.providerKeys, [provider.id]: v } });
  const [test, setTest] = useState<{ state: 'idle' | 'checking' } | { state: 'result'; ok: boolean; message: string }>({ state: 'idle' });
  const [localModels, setLocalModels] = useState<Array<{ id: string; name: string; tool_calling?: string }>>([]);
  const [deviceMsg, setDeviceMsg] = useState<string>('');
  const [modelActionState, setModelActionState] = useState<'idle' | 'downloading' | 'deleting'>('idle');
  const [modelActionMsg, setModelActionMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const [dynamicModels, setDynamicModels] = useState<Record<string, Array<{ id: string; name: string }>>>({});
  const [fetchingModels, setFetchingModels] = useState<boolean>(false);
  const [fetchMsg, setFetchMsg] = useState<string | null>(null);
  const [manualInputMode, setManualInputMode] = useState<Record<string, boolean>>({});

  const fetchLiveModels = useCallback(async (targetProviderId = provider.id, manual = false) => {
    if (targetProviderId === 'local') return;
    const key = ws.providerKeys[targetProviderId]?.trim();
    const defaultUrl = PROVIDERS.find((p) => p.id === targetProviderId)?.baseUrl ?? '';
    const url = ws.providerUrls[targetProviderId]?.trim() || defaultUrl;

    const pDef = PROVIDERS.find((p) => p.id === targetProviderId);
    if (pDef?.needsKey && !key) {
      if (manual) setFetchMsg(`Please enter your ${pDef.label} API key first.`);
      return;
    }
    if (targetProviderId === 'custom' && !url) {
      if (manual) setFetchMsg('Please enter your custom endpoint Base URL first.');
      return;
    }

    setFetchingModels(true);
    setFetchMsg('Fetching live models from provider...');
    try {
      const res = await api.fetchModels(targetProviderId, key, url);
      if (res.success && res.models && res.models.length > 0) {
        setDynamicModels((prev) => ({ ...prev, [targetProviderId]: res.models }));
        setFetchMsg(res.message || `Discovered ${res.models.length} live models.`);
        // Auto-select first model if not yet set
        if (!ws.providerModels?.[targetProviderId]) {
          const firstId = res.models[0].id;
          ws.update({ providerModels: { ...ws.providerModels, [targetProviderId]: firstId } });
        }
      } else {
        setFetchMsg(res.message || `No models returned by ${targetProviderId}. You can enter your model tag manually.`);
      }
    } catch (e) {
      setFetchMsg(e instanceof ApiError ? e.message : 'Unable to query live models.');
    } finally {
      setFetchingModels(false);
    }
  }, [provider.id, ws.providerKeys, ws.providerUrls, ws.providerModels, ws.update]);

  const refreshModels = useCallback(async () => {
    try {
      const res = await api.fetchModels('local');
      if (res.success && res.models) {
        setLocalModels(res.models);
        if (res.message) setDeviceMsg(res.message);
      }
    } catch {
      // Offline fallback
    }
  }, []);

  useEffect(() => {
    setTest({ state: 'idle' });
    setFetchMsg(null);
    if (provider.id === 'local') {
      void refreshModels();
    } else {
      // Auto-fetch models if credentials exist
      const key = ws.providerKeys[provider.id]?.trim();
      const pDef = PROVIDERS.find((p) => p.id === provider.id);
      if (!pDef?.needsKey || key) {
        void fetchLiveModels(provider.id, false);
      }
    }
  }, [provider.id, refreshModels, fetchLiveModels, ws.providerKeys]);

  const FALLBACK_GGUF_MODELS = useMemo(() => [
    { id: 'qwen2.5-3b-instruct', name: 'Qwen 2.5 3B Instruct (GGUF · 2.0 GB · Recommended · Tools: Native)', tool_calling: 'Native (Hermes / Function Calling)' },
    { id: 'qwen2.5-1.5b-instruct', name: 'Qwen 2.5 1.5B Instruct (GGUF · 1.0 GB · Fast / Low RAM · Tools: Native)', tool_calling: 'Native (Function Calling)' },
    { id: 'llama-3.2-3b-instruct', name: 'Llama 3.2 3B Instruct (GGUF · 2.0 GB · Meta 128k · Tools: Supported)', tool_calling: 'Supported (Llama 3.2 Tools)' },
    { id: 'llama-3.2-1b-instruct', name: 'Llama 3.2 1B Instruct (GGUF · 0.8 GB · Minimal RAM · Tools: Basic)', tool_calling: 'Basic (Lightweight Tools)' },
  ], []);

  const displayModels = localModels.length > 0 ? localModels : FALLBACK_GGUF_MODELS;
  const activeModelId = ws.localModel || 'qwen2.5-3b-instruct';
  const activeMeta = displayModels.find((m) => m.id === activeModelId);
  const isModelDownloaded = activeMeta ? activeMeta.name.includes('[Ready]') : false;

  const downloadSelectedModel = async () => {
    setModelActionState('downloading');
    setModelActionMsg(null);
    try {
      const res = await api.downloadModel(activeModelId);
      if (res.success) {
        setModelActionMsg({ ok: true, text: res.message });
        await refreshModels();
      } else {
        setModelActionMsg({ ok: false, text: res.message });
      }
    } catch (e) {
      setModelActionMsg({
        ok: false,
        text: e instanceof ApiError ? e.message : 'Download failed.',
      });
    } finally {
      setModelActionState('idle');
    }
  };

  const deleteSelectedModel = async () => {
    setModelActionState('deleting');
    setModelActionMsg(null);
    try {
      const res = await api.deleteModel(activeModelId);
      if (res.success) {
        setModelActionMsg({ ok: true, text: res.message });
        await refreshModels();
      } else {
        setModelActionMsg({ ok: false, text: res.message });
      }
    } catch (e) {
      setModelActionMsg({
        ok: false,
        text: e instanceof ApiError ? e.message : 'Delete failed.',
      });
    } finally {
      setModelActionState('idle');
    }
  };

  // Asks the backend to reach the chosen model with these settings; the key is sent only for this check.
  const runTest = async () => {
    setTest({ state: 'checking' });
    try {
      const activeModel = ws.providerModels?.[provider.id] || (provider.id === 'local' ? ws.localModel : DEFAULT_PROVIDER_MODELS[provider.id]);
      const r = await api.testConnection(llmConfig(provider.id, ws.providerKeys, ws.providerUrls, provider.baseUrl, activeModel)!);
      const model = provider.local ? (activeMeta?.name.split(' [')[0] ?? ws.localModel ?? 'Local GGUF') : (r.model_name ?? activeModel ?? providerName(provider.id, t, true) ?? '');
      const message = !r.success ? r.message : r.latency_ms ? t('set.testOk', { ms: r.latency_ms, model }) : t('set.testReady', { model });
      setTest({ state: 'result', ok: r.success, message });
    } catch (e) {
      setTest({ state: 'result', ok: false, message: e instanceof ApiError ? e.message : t('common.timeout') });
    }
  };

  return (
    <div className="max-w-4xl">
      <PageHeader title={t('nav.settings')} />

      <Section title={t('set.ai')}>
        <Row title={t('set.provider')} description={t('set.providerDesc')}>
          <Select value={provider.id} onValueChange={(v) => ws.update({ provider: v })}>
            <SelectTrigger className="max-w-sm" aria-label={t('set.provider')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PROVIDERS.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {providerName(p.id, t)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="mt-2 text-sm text-muted-foreground">{provider.local ? t('set.localNote') : t('set.cloudNote')}</p>
          {!provider.needsKey && <p className="mt-1 text-sm text-muted-foreground">{t('set.keyHint')}</p>}
        </Row>

        {provider.id === 'local' && (
          <Row title={t('set.model')} description={t('set.modelDesc')}>
            <Select value={activeModelId} onValueChange={(v) => { ws.update({ localModel: v }); setModelActionMsg(null); }}>
              <SelectTrigger className="max-w-md" aria-label={t('set.model')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {displayModels.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {deviceMsg && <p className="mt-2 text-xs text-muted-foreground">{deviceMsg}</p>}
            {activeMeta?.tool_calling && (
              <div className="mt-2.5 flex items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded bg-accent/70 px-2 py-0.5 text-[11px] font-mono font-medium text-foreground border border-border/50">
                  <span className="text-good font-bold">⚡</span> Tool Calling: {activeMeta.tool_calling}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  Required for financial calculation engines & ledger staging.
                </span>
              </div>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-3">
              {isModelDownloaded ? (
                <>
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-good/10 px-2.5 py-0.5 text-xs font-medium text-good-text">
                    <span className="size-1.5 rounded-full bg-good" aria-hidden />
                    {t('set.modelReady')}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={deleteSelectedModel}
                    disabled={modelActionState !== 'idle'}
                    className="h-7 text-xs text-critical-text hover:bg-critical/10"
                  >
                    {modelActionState === 'deleting' ? t('set.deleting') : t('set.deleteModel')}
                  </Button>
                </>
              ) : (
                <>
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
                    {t('set.modelNotDownloaded')}
                  </span>
                  <Button
                    variant="default"
                    size="sm"
                    onClick={downloadSelectedModel}
                    disabled={modelActionState !== 'idle'}
                    className="h-7 text-xs"
                  >
                    {modelActionState === 'downloading' ? t('set.downloading') : t('set.downloadModel')}
                  </Button>
                </>
              )}
              {modelActionMsg && (
                <span className={cn('text-xs', modelActionMsg.ok ? 'text-good-text' : 'text-critical-text')}>
                  {modelActionMsg.text}
                </span>
              )}
            </div>
          </Row>
        )}

        {(provider.id === 'custom' || provider.id === 'ollama') && (
          <Row title={t('set.endpoint')} description={provider.id === 'ollama' ? 'Default Ollama daemon address (http://localhost:11434).' : 'OpenAI-compatible Base URL ending in /v1 (e.g. http://localhost:1234/v1 or https://openrouter.ai/api/v1).'}>
            <Label htmlFor="base-url" className="sr-only">
              {t('set.endpoint')}
            </Label>
            <Input id="base-url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={provider.id === 'ollama' ? 'http://localhost:11434' : 'https://api.openai.com/v1'} className="max-w-sm font-mono text-sm" />
          </Row>
        )}

        {provider.id !== 'local' && (
          <Row title={t('set.model')} description={`Live models dynamically discovered from ${provider.label}.`}>
            {dynamicModels[provider.id]?.length && !manualInputMode[provider.id] ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Select
                    value={ws.providerModels?.[provider.id] || dynamicModels[provider.id][0].id}
                    onValueChange={(v) => ws.update({ providerModels: { ...ws.providerModels, [provider.id]: v } })}
                  >
                    <SelectTrigger className="max-w-md font-mono text-xs" aria-label={t('set.model')}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {dynamicModels[provider.id].map((m) => (
                        <SelectItem key={m.id} value={m.id} className="font-mono text-xs">
                          {m.name || m.id}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void fetchLiveModels(provider.id, true)}
                    disabled={fetchingModels}
                    className="h-9 text-xs"
                  >
                    {fetchingModels ? 'Fetching...' : 'Fetch Models'}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setManualInputMode((prev) => ({ ...prev, [provider.id]: true }))}
                    className="h-9 text-xs text-muted-foreground hover:text-foreground"
                  >
                    Type Tag
                  </Button>
                </div>
                {fetchMsg && <p className="text-xs text-good-text">{fetchMsg}</p>}
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Input
                    id="dynamic-model-input"
                    value={ws.providerModels?.[provider.id] || DEFAULT_PROVIDER_MODELS[provider.id] || ''}
                    onChange={(e) => ws.update({ providerModels: { ...ws.providerModels, [provider.id]: e.target.value } })}
                    placeholder={`e.g. ${DEFAULT_PROVIDER_MODELS[provider.id] || 'model-name'}`}
                    className="max-w-sm font-mono text-sm"
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void fetchLiveModels(provider.id, true)}
                    disabled={fetchingModels}
                    className="h-9 text-xs"
                  >
                    {fetchingModels ? 'Fetching...' : 'Fetch Models'}
                  </Button>
                  {dynamicModels[provider.id]?.length ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setManualInputMode((prev) => ({ ...prev, [provider.id]: false }))}
                      className="h-9 text-xs text-muted-foreground hover:text-foreground"
                    >
                      Show List ({dynamicModels[provider.id].length})
                    </Button>
                  ) : null}
                </div>
                {fetchMsg ? (
                  <p className="text-xs text-muted-foreground">{fetchMsg}</p>
                ) : provider.needsKey && !apiKey ? (
                  <p className="text-xs text-muted-foreground">
                    Enter your {provider.label} API key below, then click &apos;Fetch Models&apos; to load models directly from the provider.
                  </p>
                ) : provider.id === 'ollama' ? (
                  <p className="text-xs text-muted-foreground">
                    Ensure Ollama is running (&apos;ollama serve&apos;) and click &apos;Fetch Models&apos; to query pulled models.
                  </p>
                ) : provider.id === 'custom' ? (
                  <p className="text-xs text-muted-foreground">
                    Enter your Base URL above and click &apos;Fetch Models&apos; to probe /v1/models.
                  </p>
                ) : null}
              </div>
            )}
          </Row>
        )}

        {(provider.needsKey || provider.id === 'custom') && (
          <Row title={t('set.key')} description={provider.id === 'custom' ? 'API Key (Optional for local servers like LM Studio; required for authenticated cloud gateways).' : t('set.keyDesc')}>
            <Label htmlFor="api-key" className="sr-only">
              {t('set.key')}
            </Label>
            <Input id="api-key" type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={provider.id === 'custom' ? 'sk-... (optional)' : t('set.keyPh')} className="max-w-sm" />
            {!ws.isLocal && provider.needsKey && (
              <p className="mt-2 flex max-w-md items-start gap-1.5 text-sm text-warning-text">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
                {t('set.keyHosted')}
              </p>
            )}
          </Row>
        )}

        <Row title={t('set.conn')} description={t('set.connDesc')}>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="outline" onClick={runTest} disabled={test.state === 'checking'}>
              {test.state === 'checking' ? t('set.checking') : t('set.test')}
            </Button>
            {test.state === 'result' && (
              <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={fade} className={cn('text-sm', test.ok ? 'text-good-text' : 'text-critical-text')} role="status">
                {test.message}
              </motion.p>
            )}
          </div>
        </Row>
      </Section>

      <Section title={t('set.privacy')}>
        <Row title={t('set.where')} description={ws.isLocal ? t('set.whereLocal') : t('set.whereHosted')}>
          <p className="text-sm text-ink-2">{ws.isLocal ? t('set.whereLocalBody') : t('set.whereHostedBody')}</p>
        </Row>
        <Row title={t('set.sees')} description={t('set.seesDesc')}>
          <pre lang="en" className="whitespace-pre-wrap break-words rounded-md border bg-muted/50 p-4 font-mono text-xs leading-5 text-ink-2">
            {REDACTED_EXAMPLE}
          </pre>
        </Row>
        <Row title={t('set.remove')} description={t('set.removeDesc')}>
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="outline" disabled={!ws.hasData}>
                {t('set.removeBtn')}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{t('set.removeTitle')}</DialogTitle>
                <DialogDescription>{t('set.removeBody')}</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="outline">{t('set.keep')}</Button>
                </DialogClose>
                <DialogClose asChild>
                  <Button variant="destructive" onClick={ws.clearData}>
                    {t('set.removeBtn')}
                  </Button>
                </DialogClose>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </Row>
      </Section>

      <Section title={t('set.prefs')}>
        <Row title={t('set.language')} description={t('set.languageDesc')}>
          <LanguageCombobox value={ws.language} onChange={(v) => ws.update({ language: v })} />
        </Row>
        <Row title={t('set.currency')} description={t('set.currencyDesc')}>
          <CurrencyCombobox value={ws.homeCurrency} onChange={(v) => ws.update({ homeCurrency: v })} />
        </Row>
        <Row title={t('set.threshold')} description={t('set.thresholdDesc')}>
          <div className="flex items-center gap-2">
            <Label htmlFor="threshold" className="sr-only">
              {t('set.days')}
            </Label>
            <Input
              id="threshold"
              type="number"
              inputMode="numeric"
              min={1}
              max={365}
              value={ws.alertThresholdDays}
              onChange={(e) => ws.update({ alertThresholdDays: Math.max(1, Math.min(365, Number(e.target.value) || 1)) })}
              className="figures w-24"
            />
            <span className="text-sm text-muted-foreground">{t('set.days')}</span>
          </div>
        </Row>
        <Row title={t('set.theme')} description={t('set.themeDesc')}>
          <ToggleGroup type="single" variant="outline" size="sm" value={ws.theme} onValueChange={(v) => v && ws.update({ theme: v as Theme })} aria-label={t('set.theme')}>
            <ToggleGroupItem value="system">{t('theme.system')}</ToggleGroupItem>
            <ToggleGroupItem value="light">{t('theme.light')}</ToggleGroupItem>
            <ToggleGroupItem value="dark">{t('theme.dark')}</ToggleGroupItem>
          </ToggleGroup>
        </Row>
      </Section>

      <Section title={t('set.about')}>
        <div className="flex flex-col gap-6 py-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-md space-y-3">
            <div className="flex items-center gap-2.5">
              <CashPilotMark className="size-9" />
              <Wordmark name="cashpilot" height={20} />
            </div>
            <p className="text-sm text-ink-2">{t('set.aboutDesc')}</p>
            <p className="text-sm text-muted-foreground">{t('set.aboutModel')}</p>
            <a href="https://github.com/SamJU25/F-SME-Finance-Copilot" target="_blank" rel="noopener noreferrer" className="inline-block text-sm font-medium underline-offset-2 hover:underline">
              {t('set.source')}
            </a>
          </div>
          <div className="flex items-center gap-2.5">
            <BlueprintMark className="size-8" />
            <Wordmark name="blueprint" height={18} />
          </div>
        </div>
      </Section>
    </div>
  );
}
