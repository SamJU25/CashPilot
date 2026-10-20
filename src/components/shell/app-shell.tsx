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
} from 'lucide-react';
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { spring } from '@/lib/motion';
import { useIntents, useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { providerName } from '@/lib/providers';
import { useT, type Key } from '@/lib/i18n';
import { LanguageMenu } from '@/components/shell/language-menu';
import { ThemeSwitch } from '@/components/shell/theme-switch';
import { CashPilotMark, Wordmark } from '@/components/shell/brand';


const NAV: { group: Key; items: { href: string; label: Key; icon: typeof LineChart }[] }[] = [
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
    ],
  },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
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
              const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'relative flex h-9 items-center gap-2.5 rounded-md px-3 text-sm transition-colors',
                      active ? 'font-medium text-foreground' : 'text-ink-2 hover:bg-muted hover:text-foreground',
                    )}
                  >
                    {active && (
                      <motion.span layoutId="nav-active" transition={spring.snappy} className="absolute inset-0 rounded-md bg-card shadow-[0_0_0_1px_rgb(var(--border))]" />
                    )}
                    <item.icon className="relative size-4 shrink-0" aria-hidden />
                    <span className="relative">{t(item.label)}</span>
                    {item.href === '/assistant' && pending > 0 && (
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
  const { isLocal, provider, hasData, source } = useWorkspace();
  const { t } = useT();
  const pathname = usePathname();
  const providerLabel = providerName(provider, t, true) ?? t('rail.notSet');
  const [server, setServer] = useState<'checking' | 'online' | 'offline'>('checking');

  // Rechecked every 30 s, so the owner sees the backend go down before an upload or a question fails.
  useEffect(() => {
    let alive = true;
    const check = () =>
      api
        .health()
        .then(() => alive && setServer('online'))
        .catch(() => alive && setServer('offline'));
    check();
    const timer = window.setInterval(check, 30_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <div className="space-y-3 border-t pt-4">
      <div className="flex items-center gap-1">
        <LanguageMenu className="h-9 min-w-0 flex-1 rounded-md" />
        <ThemeSwitch className="size-9 shrink-0" />
      </div>
      <Link
        href="/settings"
        className={cn(
          'flex h-9 items-center gap-2.5 rounded-md px-3 text-sm text-ink-2 transition-colors hover:bg-muted hover:text-foreground',
          pathname.startsWith('/settings') && 'bg-card font-medium text-foreground shadow-[0_0_0_1px_rgb(var(--border))]',
        )}
      >
        <Settings2 className="size-4" aria-hidden />
        {t('nav.settings')}
      </Link>
      <dl className="space-y-1.5 px-3 text-xs">
        <div className="flex items-center justify-between gap-2">
          <dt className="text-muted-foreground">{t('rail.running')}</dt>
          <dd className="flex items-center gap-1.5">
            <span className={cn('size-1.5 rounded-full', isLocal ? 'bg-good' : 'bg-series-1')} aria-hidden />
            {isLocal ? t('rail.local') : t('rail.hosted')}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-muted-foreground">{t('rail.server')}</dt>
          <dd className="flex items-center gap-1.5">
            <span className={cn('size-1.5 rounded-full', server === 'online' ? 'bg-good' : server === 'offline' ? 'bg-critical' : 'bg-muted-foreground')} aria-hidden />
            {t(`rail.${server}` as Key)}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-muted-foreground">{t('rail.model')}</dt>
          <dd>{providerLabel}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-muted-foreground">{t('rail.data')}</dt>
          <dd>{!hasData ? t('rail.none') : source === 'live' ? t('rail.yours') : t('rail.sample')}</dd>
        </div>
      </dl>
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

export function AppShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const isAssistant = pathname === '/assistant';
  const { t } = useT();

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[232px_1fr]">
      <aside className="sticky top-0 hidden h-dvh flex-col gap-8 overflow-y-auto border-r bg-background px-3 py-5 lg:flex">
        <Brand />
        <div className="flex-1">
          <NavLinks />
        </div>
        <RailFooter />
      </aside>

      <div className={cn('min-w-0', isAssistant && 'flex h-dvh flex-col overflow-hidden')}>
        {/* Below lg only: the menu button opens the rail, which holds navigation, language and theme. */}
        <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between border-b bg-background/90 px-2 backdrop-blur lg:hidden">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="size-11" aria-label={t('nav.menu')}>
                <Menu />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="flex w-72 flex-col gap-8 bg-background px-3 py-5">
              <SheetTitle className="sr-only">{t('nav.menuTitle')}</SheetTitle>
              <Brand />
              <div className="flex-1">
                <NavLinks onNavigate={() => setOpen(false)} />
              </div>
              <RailFooter />
            </SheetContent>
          </Sheet>
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

