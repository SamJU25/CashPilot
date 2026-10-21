'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import {
  FileText,
  Landmark,
  LineChart,
  Menu,
  MessageSquare,
  ReceiptText,
  Settings2,
  ShieldCheck,
  SquarePen,
} from 'lucide-react';
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { spring } from '@/lib/motion';
import { useIntents, useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';
import { useT, type Key } from '@/lib/i18n';
import { CashPilotMark, Wordmark } from '@/components/shell/brand';


const NAV: { group: Key; items: { href: string; label: Key; icon: typeof LineChart; isAction?: boolean }[] }[] = [
  {
    group: 'nav.money',
    items: [
      { href: '/', label: 'nav.overview', icon: LineChart },
      { href: '/statements', label: 'nav.statements', icon: FileText },
      { href: '/receivables', label: 'nav.receivables', icon: ReceiptText },
      { href: '/funding', label: 'nav.funding', icon: Landmark },
    ],
  },
  {
    group: 'nav.copilot',
    items: [
      { href: '/assistant', label: 'nav.assistant', icon: MessageSquare },
      { href: '/sentinel', label: 'nav.sentinel', icon: ShieldCheck },
      { href: '/assistant?new=true', label: 'as.newChat', icon: SquarePen, isAction: true },
    ],
  },
];

function NavLinks({ onNavigate, id = 'desktop' }: { onNavigate?: () => void; id?: string }) {
  const pathname = usePathname();
  const { t } = useT();
  const pending = useIntents().filter((i) => i.status === 'STAGED_PENDING_HITL').length;

  return (
    <nav className="flex flex-col gap-6" aria-label={t('nav.main')}>
      {NAV.map((section) => (
        <div key={section.group}>
          <p className="px-3 pb-1.5 text-xs font-medium text-muted-foreground">{t(section.group)}</p>
          <ul className="space-y-0.5">
            {section.items.map((item) => {
              const active = item.isAction ? false : (item.href === '/' ? pathname === '/' : pathname.startsWith(item.href));
              return (
                <li key={item.label}>
                  <Link
                    href={item.href}
                    onClick={() => {
                      if (item.isAction) {
                        try {
                          window.sessionStorage.removeItem('cashpilot.chat.v2');
                        } catch {}
                        window.dispatchEvent(new CustomEvent('cashpilot:new-chat'));
                      }
                      onNavigate?.();
                    }}
                    prefetch={true}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'relative flex h-9 items-center gap-2.5 rounded-md px-3 text-sm transition-colors',
                      active ? 'font-medium text-foreground' : 'text-ink-2 hover:bg-muted hover:text-foreground',
                      item.isAction && 'text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {active && (
                      <motion.span layoutId={`nav-active-${id}`} transition={spring.snappy} className="pointer-events-none absolute inset-0 rounded-md bg-card shadow-[0_0_0_1px_rgb(var(--border))]" />
                    )}
                    <item.icon className="relative size-4 shrink-0" aria-hidden />
                    <span className="relative">{t(item.label)}</span>
                    {(item.href === '/assistant' || item.href === '/sentinel') && !item.isAction && pending > 0 && (
                      <span className="figures relative ml-auto rounded-full bg-warning/20 px-1.5 text-xs font-medium text-warning-text" aria-label={t('nav.waiting', { n: pending })}>
                        {pending}
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function RailFooter() {
  const { t } = useT();
  const pathname = usePathname();

  return (
    <div className="border-t pt-3">
      <Link
        href="/settings"
        prefetch={true}
        className={cn(
          'flex h-9 items-center gap-2.5 rounded-md px-3 text-sm text-ink-2 transition-colors hover:bg-muted hover:text-foreground',
          pathname.startsWith('/settings') && 'bg-card font-medium text-foreground shadow-[0_0_0_1px_rgb(var(--border))]',
        )}
      >
        <Settings2 className="size-4" aria-hidden />
        {t('nav.settings')}
      </Link>
    </div>
  );
}

/** Live mode is remembered per browser, but the figures are tab-scoped: a new tab has the mode and no data. */
function SessionEndedBanner() {
  const { ready, hasData, source, live, loadSample } = useWorkspace();
  const { t } = useT();
  const empty = !live.analysis && !live.underwrite && !live.receivables && live.intents.length === 0;
  if (!ready || !hasData || source !== 'live' || !empty) return null;
  return (
    <div role="status" className="mb-6 flex flex-col gap-3 rounded-lg border border-warning/40 bg-warning/10 p-4 sm:flex-row sm:items-center">
      <div className="flex-1">
        <p className="text-sm font-medium">{t('lv.endedTitle')}</p>
        <p className="text-sm text-muted-foreground">{t('lv.endedBody')}</p>
      </div>
      <div className="flex shrink-0 gap-2">
        <Button asChild size="sm">
          <Link href="/statements">{t('common.add')}</Link>
        </Button>
        <Button variant="outline" size="sm" onClick={loadSample}>
          {t('st.useSample')}
        </Button>
      </div>
    </div>
  );
}

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5 px-3" aria-label="CashPilot by Blueprint">
      <CashPilotMark className="size-8" />
      <span className="flex flex-col gap-1">
        <Wordmark name="cashpilot" height={17} />
        <span className="font-mono text-[9px] uppercase leading-none tracking-[0.2em] text-muted-foreground">by Blueprint</span>
      </span>
    </Link>
  );
}

function DemoBadge({ compact }: { compact?: boolean }) {
  const { hasData, source, clearData } = useWorkspace();
  const { t } = useT();

  if (!hasData || source !== 'sample') return null;

  const handleExit = () => {
    clearData();
    try {
      window.sessionStorage.removeItem('cashpilot.chat.v2');
    } catch {}
    window.dispatchEvent(new CustomEvent('cashpilot:new-chat'));
  };

  if (compact) {
    return (
      <div className="flex items-center gap-1.5 rounded-full border border-warning/30 bg-warning/10 px-2.5 py-1 text-xs text-warning-text">
        <span className="size-1.5 shrink-0 rounded-full bg-warning animate-pulse" aria-hidden />
        <span className="font-medium text-[11px] sm:text-xs">{t('rail.demoMode')}</span>
        <button
          type="button"
          onClick={handleExit}
          className="ml-1 rounded px-1 text-[11px] font-semibold underline underline-offset-2 hover:text-foreground transition-colors"
          title={t('rail.exitDemo')}
        >
          {t('rail.exitDemo')}
        </button>
      </div>
    );
  }

  return (
    <div className="mx-1 flex items-center justify-between gap-2 rounded-lg border border-warning/30 bg-warning/10 px-2.5 py-2 text-xs text-warning-text">
      <div className="flex items-center gap-2 min-w-0">
        <span className="size-1.5 shrink-0 rounded-full bg-warning animate-pulse" aria-hidden />
        <div className="min-w-0">
          <p className="font-semibold leading-tight text-foreground/90 truncate">{t('rail.demoMode')}</p>
          <p className="text-[10px] text-muted-foreground truncate">{t('rail.demoActive')}</p>
        </div>
      </div>
      <button
        type="button"
        onClick={handleExit}
        className="shrink-0 rounded-md border border-warning/40 bg-background/60 px-2 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-warning/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        {t('rail.exitDemo')}
      </button>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const isAssistant = pathname === '/assistant';
  const { t } = useT();

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[232px_1fr]">
      <aside className="sticky top-0 hidden h-dvh flex-col gap-6 overflow-y-auto border-r bg-background px-3 py-5 lg:flex">
        <div className="space-y-3">
          <Brand />
          <DemoBadge />
        </div>
        <div className="flex-1">
          <NavLinks />
        </div>
        <RailFooter />
      </aside>

      <div className={cn('min-w-0', isAssistant && 'flex h-dvh flex-col overflow-hidden')}>
        {/* Below lg only: the menu button opens the rail, which holds navigation, language and theme. */}
        <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between border-b bg-background/90 px-3 backdrop-blur lg:hidden">
          <div className="flex items-center gap-2">
            <Sheet open={open} onOpenChange={setOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="size-10" aria-label={t('nav.menu')}>
                  <Menu />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="flex w-72 flex-col gap-6 bg-background px-3 py-5">
                <SheetTitle className="sr-only">{t('nav.menuTitle')}</SheetTitle>
                <div className="space-y-3">
                  <Brand />
                  <DemoBadge />
                </div>
                <div className="flex-1">
                  <NavLinks onNavigate={() => setOpen(false)} id="mobile" />
                </div>
                <RailFooter />
              </SheetContent>
            </Sheet>
            <Wordmark name="cashpilot" height={15} />
          </div>
          <DemoBadge compact />
        </header>

        <main
          className={cn(
            'mx-auto w-full px-4 sm:px-8',
            isAssistant
              ? 'flex flex-1 min-h-0 flex-col max-w-[1400px] pb-2 pt-2 lg:pt-5'
              : 'max-w-[1240px] pb-8 pt-4 lg:pb-10 lg:pt-8'
          )}
        >
          <SessionEndedBanner />
          {children}
        </main>
      </div>
    </div>
  );
}

