'use client';

import { Check, Globe } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { LANGUAGES, useT } from '@/lib/i18n';
import { useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';

/** Globe button with the current language name, in the rail. */
export function LanguageMenu({ className }: { className?: string }) {
  const { language, update } = useWorkspace();
  const { t } = useT();
  const current = LANGUAGES.find((l) => l.id === language) ?? LANGUAGES[0];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={cn('w-full justify-start gap-2.5 px-3 text-ink-2 hover:bg-muted hover:text-foreground', className)}
          aria-label={`${t('lang.label')}: ${current.label}`}
        >
          <Globe className="size-4 shrink-0" aria-hidden />
          <span className="truncate">{current.label}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="min-w-56 max-h-72 overflow-y-auto">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{t('lang.label')}</DropdownMenuLabel>
        {LANGUAGES.map((l) => (
          <DropdownMenuItem
            key={l.id}
            lang={l.htmlLang}
            onSelect={() => update({ language: l.id })}
            className="justify-between gap-4 cursor-pointer"
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="w-8 font-mono text-xs uppercase text-muted-foreground shrink-0">{l.id}</span>
              <span className="font-medium text-foreground">{l.label}</span>
              {l.englishName && l.englishName !== l.label && (
                <span className="truncate text-xs text-muted-foreground">({l.englishName})</span>
              )}
            </div>
            {l.id === language && <Check className="size-4 text-primary shrink-0" aria-hidden />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
