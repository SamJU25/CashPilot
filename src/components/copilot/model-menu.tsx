'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Check, ChevronDown, Settings2, Wrench } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { useT } from '@/lib/i18n';
import { modelLabel, useActiveLocalModel } from '@/lib/local-models';
import { PROVIDERS, isProviderReady, providerName } from '@/lib/providers';
import { useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';

/**
 * Compact model chip for the chat input. Lists only models that can answer right now: GGUF files on
 * disk, and providers with their key, address or (Ollama) a fetched model. Setup stays in Settings.
 */
export function ModelMenu({ onSwitch, disabled }: { onSwitch: (id: string, localModel?: string) => void; disabled?: boolean }) {
  const { provider, localModel, providerKeys, providerUrls, providerModels } = useWorkspace();
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const { state: local, refresh, active } = useActiveLocalModel();
  // Re-read the models folder each time the menu opens so new downloads and deletions show up.
  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);
  const current = PROVIDERS.find((p) => p.id === provider) ?? PROVIDERS[0];
  // A saved pick whose file is gone is not a connected model.
  const missingLocal = current.id === 'local' && local.status !== 'loading' && !active;
  const currentLabel = current.id === 'local' ? (active ? `Local (${modelLabel(active)})` : missingLocal ? t('as.noModel') : t('provider.localShort')) : providerName(current.id, t, true);

  const remote = PROVIDERS.filter(
    (p) => p.id !== 'local' && isProviderReady(p.id, providerKeys, providerUrls) && (p.id !== 'ollama' || Boolean(providerModels?.ollama)),
  );
  const localModels = local.status === 'ready' ? local.models : [];
  const nothing = local.status !== 'loading' && localModels.length === 0 && remote.length === 0;

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="ghost" size="sm" disabled={disabled} className="h-8 gap-1.5 rounded-full px-2.5 text-xs text-ink-2" aria-label={`${t('as.model')}: ${currentLabel}`}>
          <span className={cn('size-1.5 rounded-full', missingLocal ? 'bg-muted-foreground' : current.local ? 'bg-good' : 'bg-series-1')} aria-hidden />
          {currentLabel}
          {!missingLocal && <span className="text-muted-foreground">{current.local ? t('as.modelLocal') : t('as.modelCloud')}</span>}
          <ChevronDown className="size-3.5 text-muted-foreground" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-80">
        {local.status === 'loading' && (
          <div className="space-y-1.5 p-2" aria-busy="true">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        )}

        {localModels.length > 0 && (
          <>
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{t('provider.local')}</DropdownMenuLabel>
            {localModels.map((m) => {
              const selected = provider === 'local' && localModel === m.id;
              return (
                <DropdownMenuItem key={m.id} onSelect={() => !selected && onSwitch('local', m.id)} className="items-start gap-2.5 py-2">
                  <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-good" aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm">{modelLabel(m)}</span>
                    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      {[m.quant, m.size_gb ? `${m.size_gb} GB` : null].filter(Boolean).join(' · ') || t('as.modelLocal')}
                      {m.tool_calling && <Wrench className="size-3 text-good-text" aria-label="Tool calling" />}
                    </span>
                  </span>
                  {selected && <Check className="mt-0.5 size-4 text-primary" aria-hidden />}
                </DropdownMenuItem>
              );
            })}
          </>
        )}

        {remote.length > 0 && (
          <>
            {localModels.length > 0 && <DropdownMenuSeparator />}
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{t('as.model')}</DropdownMenuLabel>
            {remote.map((p) => (
              <DropdownMenuItem key={p.id} onSelect={() => p.id !== provider && onSwitch(p.id)} className="items-start gap-2.5 py-2">
                <span className={cn('mt-1.5 size-1.5 shrink-0 rounded-full', p.local ? 'bg-good' : 'bg-series-1')} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm">{providerName(p.id, t)}</span>
                  <span className="block truncate font-mono text-xs text-muted-foreground">{providerModels?.[p.id] || (p.local ? t('as.modelLocal') : t('as.modelCloud'))}</span>
                </span>
                {p.id === provider && <Check className="mt-0.5 size-4 text-primary" aria-hidden />}
              </DropdownMenuItem>
            ))}
          </>
        )}

        {nothing && <p className="px-2 py-3 text-xs text-muted-foreground">No models connected yet. Download a local model or add a provider key in Settings.</p>}

        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings" className="gap-2 text-sm">
            <Settings2 className="size-4" aria-hidden />
            {t('as.manage')}
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
