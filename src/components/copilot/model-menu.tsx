'use client';

import Link from 'next/link';
import { Check, ChevronDown, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useT } from '@/lib/i18n';
import { PROVIDERS, isProviderReady, providerName } from '@/lib/providers';
import { useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';

/**
 * Compact model chip for the chat input. Only models that can answer are selectable; keys and
 * endpoints stay in Settings so the chat never becomes a second configuration screen.
 */
export function ModelMenu({ onSwitch, disabled }: { onSwitch: (id: string) => void; disabled?: boolean }) {
  const { provider, localModel, providerKeys, providerUrls } = useWorkspace();
  const { t } = useT();
  const current = PROVIDERS.find((p) => p.id === provider) ?? PROVIDERS[0];
  const currentLabel = current.local && localModel ? `Local (${localModel.replace('-instruct', '')})` : providerName(current.id, t, true);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="ghost" size="sm" disabled={disabled} className="h-8 gap-1.5 rounded-full px-2.5 text-xs text-ink-2" aria-label={`${t('as.model')}: ${currentLabel}`}>
          <span className={cn('size-1.5 rounded-full', current.local ? 'bg-good' : 'bg-series-1')} aria-hidden />
          {currentLabel}
          <span className="text-muted-foreground">{current.local ? t('as.modelLocal') : t('as.modelCloud')}</span>
          <ChevronDown className="size-3.5 text-muted-foreground" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-72">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{t('as.model')}</DropdownMenuLabel>
        {PROVIDERS.map((p) => {
          const ready = isProviderReady(p.id, providerKeys, providerUrls);
          const pLabel = p.local && localModel ? `Local GGUF (${localModel.replace('-instruct', '')})` : providerName(p.id, t);
          return (
            <DropdownMenuItem key={p.id} disabled={!ready} onSelect={() => ready && p.id !== provider && onSwitch(p.id)} className="items-start gap-2.5 py-2">
              <span className={cn('mt-1.5 size-1.5 shrink-0 rounded-full', p.local ? 'bg-good' : 'bg-series-1')} aria-hidden />
              <span className="flex-1">
                <span className="block text-sm">{pLabel}</span>
                <span className="block text-xs text-muted-foreground">{!ready ? t('as.addKey') : p.local ? t('as.modelLocal') : t('as.modelCloud')}</span>
              </span>
              {p.id === provider && <Check className="mt-0.5 size-4 text-primary" aria-hidden />}
            </DropdownMenuItem>
          );
        })}
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
