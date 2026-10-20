'use client';

import { useEffect, useMemo, useState } from 'react';
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
import { PROVIDERS, providerName } from '@/lib/providers';
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

  useEffect(() => {
    setTest({ state: 'idle' });
  }, [provider]);

  // Asks the backend to reach the chosen model with these settings; the key is sent only for this check.
  const runTest = async () => {
    setTest({ state: 'checking' });
    try {
      const r = await api.testConnection(llmConfig(provider.id, ws.providerKeys, ws.providerUrls, provider.baseUrl)!);
      // The local model is checked on disk without generating, so it has no round-trip time to show.
      const model = provider.local ? (providerName(provider.id, t, true) ?? '') : (r.model_name ?? providerName(provider.id, t, true) ?? '');
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

        {(provider.id === 'custom' || provider.id === 'ollama') && (
          <Row title={t('set.endpoint')} description={t('set.endpointDesc')}>
            <Label htmlFor="base-url" className="sr-only">
              {t('set.endpoint')}
            </Label>
            <Input id="base-url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://" className="max-w-sm" />
          </Row>
        )}

        {provider.needsKey && (
          <Row title={t('set.key')} description={t('set.keyDesc')}>
            <Label htmlFor="api-key" className="sr-only">
              {t('set.key')}
            </Label>
            <Input id="api-key" type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={t('set.keyPh')} className="max-w-sm" />
            {!ws.isLocal && (
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
