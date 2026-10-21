'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { AlertCircle, AlertTriangle, Check, CheckCircle2, ChevronsUpDown, ExternalLink, Globe, RotateCw, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
import { HardwarePanel, LocalModelManager } from '@/components/settings/local-models';
import { BlueprintMark, CashPilotMark, Wordmark } from '@/components/shell/brand';
import { LANGUAGES, useT, type Key, type Lang } from '@/lib/i18n';
import { useHardware } from '@/lib/local-models';
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

const SECTIONS: { id: string; label: Key; description?: Key }[] = [
  { id: 'ai', label: 'set.ai', description: 'set.aiDesc' },
  { id: 'privacy', label: 'set.privacy', description: 'set.privacyDesc' },
  { id: 'prefs', label: 'set.prefs', description: 'set.prefsDesc' },
  { id: 'about', label: 'set.about' },
];

function Row({ title, description, htmlFor, children }: { title: string; description?: string; htmlFor?: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-3 py-5 md:grid-cols-[minmax(0,240px)_1fr] md:gap-8">
      <div>
        {htmlFor ? (
          <Label htmlFor={htmlFor} className="text-sm font-medium">
            {title}
          </Label>
        ) : (
          <h3 className="text-sm font-medium">{title}</h3>
        )}
        {description && <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function SectionHeading({ title, description }: { title: string; description?: string }) {
  if (!description) return <h2 className="sr-only">{title}</h2>;
  return (
    // The selected tab already shows the title; screen readers still get a heading for the panel.
    <div className="border-b pb-4">
      <h2 className="sr-only">{title}</h2>
      {description && <p className="text-sm text-muted-foreground">{description}</p>}
    </div>
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
        <Button variant="outline" role="combobox" aria-expanded={open} aria-label={t('set.language')} className="w-full max-w-sm justify-between font-normal">
          <span className="flex min-w-0 items-center gap-2 truncate">
            <Globe className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <span className="font-medium text-foreground">{current.label}</span>
            {current.englishName && current.englishName !== current.label && <span className="truncate text-muted-foreground">{current.englishName}</span>}
          </span>
          <ChevronsUpDown className="ml-2 size-4 shrink-0 opacity-50" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(360px,calc(100vw-2rem))] p-2" align="start">
        <div className="relative mb-2">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
          <Input placeholder={t('set.searchLang')} value={search} onChange={(e) => setSearch(e.target.value)} className="h-9 pl-8 text-base sm:text-sm" aria-label={t('set.searchLang')} autoFocus />
        </div>
        <ScrollArea className="max-h-64 overflow-y-auto pr-1">
          {filtered.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">{t('set.noMatch', { q: search })}</p>
          ) : (
            <div className="space-y-0.5" role="listbox" aria-label={t('set.language')}>
              {filtered.map((l) => {
                const selected = l.id === value;
                return (
                  <button
                    key={l.id}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    onClick={() => {
                      onChange(l.id as Lang);
                      setOpen(false);
                      setSearch('');
                    }}
                    className={cn(
                      'flex w-full items-center justify-between rounded px-2.5 py-2 text-left text-sm transition-colors hover:bg-accent focus:bg-accent focus:outline-none',
                      selected && 'bg-accent font-medium'
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="font-medium">{l.label}</span>
                      {l.englishName && l.englishName !== l.label && <span className="truncate text-muted-foreground">{l.englishName}</span>}
                    </span>
                    {selected && <Check className="ml-2 size-4 shrink-0 text-primary" aria-hidden />}
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
      (c) => c.code.toLowerCase().includes(q) || c.name.toLowerCase().includes(q) || c.symbol.toLowerCase().includes(q) || c.region.toLowerCase().includes(q)
    );
  }, [search]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" role="combobox" aria-expanded={open} aria-label={t('set.currency')} className="w-full max-w-sm justify-between font-normal">
          <span className="flex min-w-0 items-center gap-2 truncate">
            <span className="font-mono font-medium text-foreground">{current.code}</span>
            <span className="truncate text-muted-foreground">{current.name}</span>
          </span>
          <ChevronsUpDown className="ml-2 size-4 shrink-0 opacity-50" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(360px,calc(100vw-2rem))] p-2" align="start">
        <div className="relative mb-2">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
          <Input placeholder={t('set.searchCur')} value={search} onChange={(e) => setSearch(e.target.value)} className="h-9 pl-8 text-base sm:text-sm" aria-label={t('set.searchCur')} autoFocus />
        </div>
        <ScrollArea className="max-h-64 overflow-y-auto pr-1">
          {filtered.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">{t('set.noMatch', { q: search })}</p>
          ) : (
            <div className="space-y-0.5" role="listbox" aria-label={t('set.currency')}>
              {filtered.map((c) => {
                const selected = c.code === value;
                return (
                  <button
                    key={c.code}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    onClick={() => {
                      onChange(c.code);
                      setOpen(false);
                      setSearch('');
                    }}
                    className={cn(
                      'flex w-full items-center justify-between rounded px-2.5 py-2 text-left text-sm transition-colors hover:bg-accent focus:bg-accent focus:outline-none',
                      selected && 'bg-accent font-medium'
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="w-10 shrink-0 font-mono font-medium">{c.code}</span>
                      <span className="w-6 shrink-0 text-center text-muted-foreground">{c.symbol}</span>
                      <span className="truncate text-ink-2">{c.name}</span>
                    </span>
                    {selected && <Check className="ml-2 size-4 shrink-0 text-primary" aria-hidden />}
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

type FetchState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'found'; n: number }
  | { kind: 'none' }
  | { kind: 'needKey' }
  | { kind: 'needUrl' }
  | { kind: 'error'; message: string };

/** Model picker for cloud, Ollama and custom providers: the live list when it loads, a typed ID otherwise. */
function RemoteModelPicker() {
  const ws = useWorkspace();
  const { t } = useT();
  const provider = PROVIDERS.find((p) => p.id === ws.provider) ?? PROVIDERS[0];
  const [lists, setLists] = useState<Record<string, Array<{ id: string; name: string }>>>({});
  const [manual, setManual] = useState<Record<string, boolean>>({});
  const [fetchState, setFetchState] = useState<FetchState>({ kind: 'idle' });
  const key = ws.providerKeys[provider.id]?.trim();
  const url = ws.providerUrls[provider.id]?.trim() || provider.baseUrl;
  const selected = ws.providerModels?.[provider.id] || '';
  const setSelected = (v: string) => ws.update({ providerModels: { ...ws.providerModels, [provider.id]: v } });

  const load = useCallback(async () => {
    if (provider.needsKey && !key) return setFetchState({ kind: 'needKey' });
    if (provider.id === 'custom' && !url) return setFetchState({ kind: 'needUrl' });
    setFetchState({ kind: 'loading' });
    try {
      const res = await api.fetchModels(provider.id, key, url);
      if (res.success && res.models.length > 0) {
        setLists((prev) => ({ ...prev, [provider.id]: res.models }));
        setFetchState({ kind: 'found', n: res.models.length });
        if (!ws.providerModels?.[provider.id]) ws.update({ providerModels: { ...ws.providerModels, [provider.id]: res.models[0].id } });
      } else {
        setFetchState(res.success ? { kind: 'none' } : { kind: 'error', message: res.message || t('set.modelsError') });
      }
    } catch (e) {
      setFetchState({ kind: 'error', message: e instanceof ApiError ? e.message : t('set.modelsError') });
    }
    // ws.update and ws.providerModels change on every keystroke; the list only depends on where it is fetched from.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider.id, provider.needsKey, key, url]);

  useEffect(() => {
    void load();
  }, [load]);

  const list = lists[provider.id];
  const typing = manual[provider.id] || !list?.length;
  const status =
    fetchState.kind === 'loading'
      ? t('set.modelsLoading')
      : fetchState.kind === 'found'
        ? t('set.modelsFound', { n: fetchState.n })
        : fetchState.kind === 'needKey'
          ? t('set.needKey')
          : fetchState.kind === 'needUrl'
            ? t('set.needUrl')
            : fetchState.kind === 'none'
              ? provider.id === 'ollama'
                ? t('set.ollamaHint')
                : t('set.modelsNone')
              : fetchState.kind === 'error'
                ? fetchState.message
                : null;

  return (
    <div className="space-y-2">
      <div className="flex max-w-md items-center gap-2">
        {typing ? (
          <Input
            id="model-id"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            placeholder={DEFAULT_PROVIDER_MODELS[provider.id] || t('set.modelId')}
            aria-label={t('set.modelId')}
            className="font-mono text-sm"
          />
        ) : (
          <Select value={selected || list[0].id} onValueChange={setSelected}>
            <SelectTrigger className="font-mono text-sm" aria-label={t('set.modelPick')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {list.map((m) => (
                <SelectItem key={m.id} value={m.id} className="font-mono text-sm">
                  {m.name || m.id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <Button variant="outline" size="icon" className="shrink-0" onClick={() => void load()} disabled={fetchState.kind === 'loading'} aria-label={t('set.refreshModels')} title={t('set.refreshModels')}>
          <RotateCw className={cn('size-4', fetchState.kind === 'loading' && 'animate-spin')} aria-hidden />
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        {status && (
          <span role="status" className={cn(fetchState.kind === 'error' ? 'text-critical-text' : 'text-muted-foreground')}>
            {status}
          </span>
        )}
        {list?.length ? (
          <button type="button" onClick={() => setManual((m) => ({ ...m, [provider.id]: !typing }))} className="font-medium text-ink-2 underline-offset-2 hover:text-foreground hover:underline">
            {typing ? t('set.listModels') : t('set.typeModel')}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function AiSection() {
  const ws = useWorkspace();
  const { t } = useT();
  const provider = PROVIDERS.find((p) => p.id === ws.provider) ?? PROVIDERS[0];
  const { hw, refresh: refreshHw } = useHardware();
  const [test, setTest] = useState<{ state: 'idle' | 'checking' } | { state: 'result'; ok: boolean; message: string }>({ state: 'idle' });
  const baseUrl = ws.providerUrls[provider.id] ?? provider.baseUrl;
  const apiKey = ws.providerKeys[provider.id] ?? '';

  useEffect(() => setTest({ state: 'idle' }), [provider.id]);

  // Asks the backend to reach the chosen model with these settings; the key is sent only for this check.
  const runTest = async () => {
    setTest({ state: 'checking' });
    try {
      const activeModel = ws.providerModels?.[provider.id] || (provider.id === 'local' ? ws.localModel : DEFAULT_PROVIDER_MODELS[provider.id]);
      const r = await api.testConnection(llmConfig(provider.id, ws.providerKeys, ws.providerUrls, provider.baseUrl, activeModel)!);
      const model = provider.id === 'local' ? ws.localModel || t('provider.localShort') : (r.model_name ?? activeModel ?? providerName(provider.id, t, true) ?? '');
      const message = !r.success ? r.message : r.latency_ms ? t('set.testOk', { ms: r.latency_ms, model }) : t('set.testReady', { model });
      setTest({ state: 'result', ok: r.success, message });
    } catch (e) {
      setTest({ state: 'result', ok: false, message: e instanceof ApiError ? e.message : t('common.timeout') });
    }
  };

  return (
    <div className="divide-y">
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
        <p className="mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">{provider.local ? t('set.localNote') : t('set.cloudNote')}</p>
      </Row>

      {provider.id === 'local' ? (
        <>
          <Row title={t('set.localModels')} description={t('set.modelDesc')}>
            <LocalModelManager hw={hw} onHardwareChange={() => void refreshHw()} />
          </Row>
          <Row title={t('set.memory')} description={t('set.memoryDesc')}>
            <HardwarePanel hw={hw} onRefresh={() => void refreshHw()} />
          </Row>
        </>
      ) : (
        <>
          {(provider.id === 'custom' || provider.id === 'ollama') && (
            <Row title={t('set.endpoint')} description={provider.id === 'ollama' ? t('set.endpointDescOllama') : t('set.endpointDesc')} htmlFor="base-url">
              <Input
                id="base-url"
                value={baseUrl}
                onChange={(e) => ws.update({ providerUrls: { ...ws.providerUrls, [provider.id]: e.target.value } })}
                placeholder={provider.id === 'ollama' ? 'http://localhost:11434' : 'http://localhost:1234/v1'}
                className="max-w-md font-mono text-sm"
              />
            </Row>
          )}
          {(provider.needsKey || provider.id === 'custom') && (
            <Row title={t('set.key')} description={provider.id === 'custom' ? t('set.keyDescCustom') : t('set.keyDesc')} htmlFor="api-key">
              <Input
                id="api-key"
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={(e) => ws.update({ providerKeys: { ...ws.providerKeys, [provider.id]: e.target.value } })}
                placeholder={provider.id === 'custom' ? t('set.keyPhOptional') : t('set.keyPh')}
                className="max-w-md font-mono text-sm"
              />
              {!ws.isLocal && provider.needsKey && (
                <p className="mt-2 flex max-w-md items-start gap-1.5 text-sm text-warning-text">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
                  {t('set.keyHosted')}
                </p>
              )}
            </Row>
          )}
          <Row title={t('set.model')} description={t('set.modelCloudDesc', { provider: providerName(provider.id, t, true) ?? provider.label })}>
            <RemoteModelPicker />
          </Row>
        </>
      )}

      <Row title={t('set.conn')} description={t('set.connDesc')}>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" onClick={runTest} disabled={test.state === 'checking'}>
            {test.state === 'checking' && <RotateCw className="size-4 animate-spin" aria-hidden />}
            {test.state === 'checking' ? t('set.checking') : t('set.test')}
          </Button>
          {test.state === 'result' && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={fade}
              role="status"
              className={cn('flex max-w-md items-start gap-1.5 text-sm', test.ok ? 'text-good-text' : 'text-critical-text')}
            >
              {test.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden /> : <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />}
              {test.message}
            </motion.p>
          )}
        </div>
      </Row>
    </div>
  );
}

function PrivacySection() {
  const ws = useWorkspace();
  const { t } = useT();
  const provider = PROVIDERS.find((p) => p.id === ws.provider) ?? PROVIDERS[0];
  const savedKeys = Object.values(ws.providerKeys).filter((k) => k?.trim()).length;

  return (
    <div className="divide-y">
      <Row title={t('set.where')} description={ws.isLocal ? t('set.whereLocal') : t('set.whereHosted')}>
        <p className="max-w-md text-sm leading-relaxed text-ink-2">{ws.isLocal ? t('set.whereLocalBody') : t('set.whereHostedBody')}</p>
      </Row>

      {/* Only a cloud provider receives text; with a local model there is nothing to show. */}
      {!provider.local && (
        <Row title={t('set.sees')} description={t('set.seesDesc')}>
          <pre lang="en" className="whitespace-pre-wrap break-words rounded-md border bg-muted/50 p-4 font-mono text-xs leading-5 text-ink-2">
            {REDACTED_EXAMPLE}
          </pre>
        </Row>
      )}

      <Row title={t('set.keys')} description={t('set.keysDesc')}>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-ink-2">{savedKeys ? t('set.keysCount', { n: savedKeys }) : t('set.keysNone')}</span>
          {savedKeys > 0 && (
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="outline">{t('set.keysRemove')}</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>{t('set.keysTitle')}</DialogTitle>
                  <DialogDescription>{t('set.keysBody')}</DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <DialogClose asChild>
                    <Button variant="outline">{t('set.keysKeep')}</Button>
                  </DialogClose>
                  <DialogClose asChild>
                    <Button variant="destructive" onClick={() => ws.update({ providerKeys: {} })}>
                      {t('set.keysRemove')}
                    </Button>
                  </DialogClose>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}
        </div>
      </Row>

      <Row title={t('set.remove')} description={t('set.removeDesc')}>
        <Dialog>
          <DialogTrigger asChild>
            <Button variant="outline" disabled={!ws.hasData} className="border-critical/40 text-critical-text hover:bg-critical/10 hover:text-critical-text">
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
    </div>
  );
}

function PreferencesSection() {
  const ws = useWorkspace();
  const { t } = useT();
  return (
    <div className="divide-y">
      <Row title={t('set.language')} description={t('set.languageDesc')}>
        <LanguageCombobox value={ws.language} onChange={(v) => ws.update({ language: v })} />
      </Row>
      <Row title={t('set.currency')} description={t('set.currencyDesc')}>
        <CurrencyCombobox value={ws.homeCurrency} onChange={(v) => ws.update({ homeCurrency: v })} />
      </Row>
      <Row title={t('set.theme')} description={t('set.themeDesc')}>
        <ToggleGroup type="single" variant="outline" value={ws.theme} onValueChange={(v) => v && ws.update({ theme: v as Theme })} aria-label={t('set.theme')} className="justify-start">
          <ToggleGroupItem value="system" className="px-4">{t('theme.system')}</ToggleGroupItem>
          <ToggleGroupItem value="light" className="px-4">{t('theme.light')}</ToggleGroupItem>
          <ToggleGroupItem value="dark" className="px-4">{t('theme.dark')}</ToggleGroupItem>
        </ToggleGroup>
      </Row>
    </div>
  );
}

function AboutFact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-3.5 sm:grid-cols-[160px_minmax(0,1fr)] sm:gap-6">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm text-foreground">{children}</dd>
    </div>
  );
}

function AboutSection() {
  const { t } = useT();
  // The backend reports the release it runs; the app and server ship together under one version.
  const [version, setVersion] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    api.health().then((h) => setVersion(h.version)).catch(() => setVersion(null));
  }, []);

  return (
    <div className="pt-6">
      <div className="flex items-center gap-4">
        <CashPilotMark className="size-12" />
        <div className="min-w-0">
          <Wordmark name="cashpilot" height={22} />
          <div className="figures mt-1.5 text-sm text-muted-foreground">
            {version === undefined ? <Skeleton className="h-4 w-24" /> : version ? t('set.aboutVersion', { v: version }) : t('set.aboutVersionOffline')}
          </div>
        </div>
      </div>
      <p className="mt-4 max-w-lg text-sm leading-relaxed text-ink-2">{t('set.aboutTagline')}</p>

      <dl className="mt-6 divide-y border-y">
        <AboutFact label={t('set.aboutBy')}>
          <span className="inline-flex items-center gap-2">
            <BlueprintMark className="size-5" />
            <span className="font-medium">Blueprint</span>
          </span>
        </AboutFact>
        <AboutFact label={t('set.aboutFor')}>{t('set.aboutForValue')}</AboutFact>
        <AboutFact label={t('set.aboutRuntime')}>{t('set.aboutRuntimeValue')}</AboutFact>
        <AboutFact label={t('set.aboutSource')}>
          <a
            href="https://github.com/SamJU25/F-SME-Finance-Copilot"
            target="_blank"
            rel="noopener noreferrer"
            aria-label={t('set.source')}
            className="inline-flex max-w-full items-center gap-1.5 font-medium underline-offset-2 hover:underline"
          >
            <span className="truncate font-mono text-[13px]">SamJU25/F-SME-Finance-Copilot</span>
            <ExternalLink className="size-3.5 shrink-0" aria-hidden />
          </a>
        </AboutFact>
      </dl>
    </div>
  );
}

const isSection = (id: string) => SECTIONS.some((s) => s.id === id);

export default function SettingsPage() {
  const { t } = useT();
  const [tab, setTab] = useState('ai');

  // The open section lives in the URL hash so links like /settings#privacy land on it.
  useEffect(() => {
    const fromHash = () => {
      const id = window.location.hash.slice(1);
      if (isSection(id)) setTab(id);
    };
    fromHash();
    window.addEventListener('hashchange', fromHash);
    return () => window.removeEventListener('hashchange', fromHash);
  }, []);

  const select = (id: string) => {
    setTab(id);
    window.history.replaceState(null, '', `#${id}`);
  };

  return (
    <div className="max-w-5xl">
      <PageHeader title={t('nav.settings')} />
      <Tabs value={tab} onValueChange={select} orientation="vertical" className="lg:grid lg:grid-cols-[180px_minmax(0,1fr)] lg:gap-12">
        <TabsList
          aria-label={t('set.sections')}
          className="-mx-4 flex h-auto w-[calc(100%+2rem)] justify-start gap-1 overflow-x-auto rounded-none border-b bg-transparent px-4 pb-2 lg:sticky lg:top-6 lg:mx-0 lg:w-full lg:flex-col lg:items-stretch lg:self-start lg:border-b-0 lg:p-0"
        >
          {SECTIONS.map((s) => (
            <TabsTrigger
              key={s.id}
              value={s.id}
              className="h-9 shrink-0 justify-start rounded-md px-3 text-sm font-medium text-ink-2 transition-colors hover:bg-muted/60 hover:text-foreground data-[state=active]:bg-muted data-[state=active]:text-foreground data-[state=active]:shadow-none"
            >
              {t(s.label)}
            </TabsTrigger>
          ))}
        </TabsList>

        {SECTIONS.map((s) => (
          <TabsContent key={s.id} value={s.id} className="mt-6 min-w-0 lg:mt-0">
            <SectionHeading title={s.id === 'about' ? t('set.aboutTitle') : t(s.label)} description={s.description && t(s.description)} />
            {s.id === 'ai' && <AiSection />}
            {s.id === 'privacy' && <PrivacySection />}
            {s.id === 'prefs' && <PreferencesSection />}
            {s.id === 'about' && <AboutSection />}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
