'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { createContext, useContext, useEffect, useState } from 'react';
import { motion } from 'motion/react';
import {
  FileText,
  Landmark,
  LineChart,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  MessageSquare,
  ReceiptText,
  Settings2,
  ShieldCheck,
} from 'lucide-react';
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { spring } from '@/lib/motion';
import { useIntents, useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';
import { useT, type Key } from '@/lib/i18n';
import { CashPilotMark, Wordmark } from '@/components/shell/brand';
import { formatDate } from '@/lib/format';
import { todayIso } from '@/lib/live-forecast';
import { ANALYSIS, TODAY } from '@/lib/mock/demo';


// Two groups: the money pages, then the two places CashPilot acts for you. Starting a chat lives on the Assistant page.
const RAIL_KEY = 'cashpilot.rail.collapsed';
const NavContext = createContext<{
  pendingHref: string | null;
  setPendingHref: (href: string | null) => void;
}>({ pendingHref: null, setPendingHref: () => {} });


const NAV: { href: string; label: Key; icon: typeof LineChart }[][] = [
  [
    { href: '/', label: 'nav.overview', icon: LineChart },
    { href: '/statements', label: 'nav.statements', icon: FileText },
    { href: '/receivables', label: 'nav.receivables', icon: ReceiptText },
    { href: '/funding', label: 'nav.funding', icon: Landmark },
  ],
  [
    { href: '/assistant', label: 'nav.assistant', icon: MessageSquare },
    { href: '/sentinel', label: 'nav.sentinel', icon: ShieldCheck },
  ],
];

function NavLinks({ onNavigate, id = 'desktop' }: { onNavigate?: () => void; id?: string }) {
  const pathname = usePathname();
  const { pendingHref, setPendingHref } = useContext(NavContext);
  const effective = pendingHref ?? pathname;
  const { t } = useT();
  const pending = useIntents().filter((i) => i.status === 'STAGED_PENDING_HITL').length;

  return (
    <nav aria-label={t('nav.main')}>
      {NAV.map((group, g) => (
        <ul key={g} className={cn('space-y-0.5', g > 0 && 'mt-4 border-t pt-4')}>
          {group.map((item) => {
            const active = item.href === '/' ? effective === '/' : effective.startsWith(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  prefetch={true}
                  onClick={() => {
                    if (item.href !== pathname) setPendingHref(item.href);
                    onNavigate?.();
                  }}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'relative flex h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors',
                    active ? 'font-medium text-foreground' : 'text-ink-2 hover:bg-muted hover:text-foreground',
                  )}
                >
                  {active && (
                    <motion.span layoutId={`nav-active-${id}`} transition={spring.snappy} className="pointer-events-none absolute inset-0 rounded-lg bg-card shadow-[0_0_0_1px_rgb(var(--border))]" />
                  )}
                  {active && <motion.span layoutId={`nav-tick-${id}`} transition={spring.snappy} className="absolute inset-y-2.5 left-0 w-0.5 rounded-full bg-primary" aria-hidden />}
                  <item.icon className={cn('relative size-4 shrink-0', active && 'text-primary')} aria-hidden />
                  <span className="relative">{t(item.label)}</span>
                  {/* The decision itself happens in the Assistant, so the count shows there only. */}
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
      ))}
    </nav>
  );
}

/** How old the figures are, since every page is only as current as the last statement. */
function DataFreshness() {
  const { hasData, source, live } = useWorkspace();
  const { t } = useT();
  const end = source === 'sample' ? ANALYSIS.end_date : live.analysis?.end_date;
  if (!hasData || !end) return null;
  const age = Math.round((Date.parse(source === 'sample' ? TODAY : todayIso()) - Date.parse(end)) / 86_400_000);
  const stale = age > 31;
  return (
    <Link href="/statements" className="mb-2 flex items-start gap-2.5 rounded-lg px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
      <span className={cn('mt-1 size-1.5 shrink-0 rounded-full', stale ? 'bg-warning' : 'bg-good')} aria-hidden />
      <span>
        <span className="block text-ink-2">{t('rail.dataTo', { date: formatDate(end, true) })}</span>
        {t(stale ? 'rail.dataStale' : 'rail.dataAge', { n: age })}
      </span>
    </Link>
  );
}

function RailFooter() {
  const { t } = useT();
  const pathname = usePathname();
  const { pendingHref, setPendingHref } = useContext(NavContext);
  const effective = pendingHref ?? pathname;

  return (
    <div>
      <DataFreshness />
      <div className="border-t pt-3">
        <Link
          href="/settings"
          prefetch={true}
          onClick={() => {
            if (pathname !== '/settings') setPendingHref('/settings');
          }}
          className={cn(
            'flex h-10 items-center gap-3 rounded-lg px-3 text-sm text-ink-2 transition-colors hover:bg-muted hover:text-foreground',
            effective.startsWith('/settings') && 'bg-card font-medium text-foreground shadow-[0_0_0_1px_rgb(var(--border))]',
          )}
        >
          <Settings2 className="size-4" aria-hidden />
          {t('nav.settings')}
        </Link>
      </div>
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
        <span className="size-1.5 shrink-0 rounded-full bg-warning" aria-hidden />
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
        <span className="size-1.5 shrink-0 rounded-full bg-warning" aria-hidden />
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

/** The rail folded to icons, so wide dashboards get the room; labels move into tooltips. */
function MiniRail({ onExpand }: { onExpand: () => void }) {
  const pathname = usePathname();
  const { pendingHref, setPendingHref } = useContext(NavContext);
  const effective = pendingHref ?? pathname;
  const { t } = useT();
  const pending = useIntents().filter((i) => i.status === 'STAGED_PENDING_HITL').length;
  const { hasData, source } = useWorkspace();
  const item = (href: string, label: string, Icon: typeof LineChart, active: boolean, dot = false) => (
    <Tooltip key={href}>
      <TooltipTrigger asChild>
        <Link
          href={href}
          prefetch={true}
          onClick={() => {
            if (href !== pathname) setPendingHref(href);
          }}
          aria-label={label}
          aria-current={active ? 'page' : undefined}
          className={cn('relative flex size-10 items-center justify-center rounded-lg transition-colors', active ? 'bg-card text-primary shadow-[0_0_0_1px_rgb(var(--border))]' : 'text-ink-2 hover:bg-muted hover:text-foreground')}
        >
          <Icon className="size-4" aria-hidden />
          {dot && <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-warning ring-2 ring-background" aria-hidden />}
        </Link>
      </TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
  return (
    <div className="flex h-full flex-col items-center gap-4">
      <Link href="/" aria-label="CashPilot by Blueprint">
        <CashPilotMark className="size-8" />
      </Link>
      {hasData && source === 'sample' && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span tabIndex={0} role="status" className="size-2 rounded-full bg-warning focus:outline-none" aria-label={t('rail.demoMode')} />
          </TooltipTrigger>
          <TooltipContent side="right">{t('rail.demoMode')}</TooltipContent>
        </Tooltip>
      )}
      <nav aria-label={t('nav.main')} className="flex flex-1 flex-col items-center">
        {NAV.map((group, g) => (
          <div key={g} className={cn('flex flex-col items-center gap-1', g > 0 && 'mt-4 border-t pt-4')}>
            {group.map((n) => item(n.href, t(n.label), n.icon, n.href === '/' ? effective === '/' : effective.startsWith(n.href), n.href === '/assistant' && pending > 0))}
          </div>
        ))}
      </nav>
      {item('/settings', t('nav.settings'), Settings2, effective.startsWith('/settings'))}
      <Button variant="ghost" size="icon" onClick={onExpand} aria-label={t('rail.expand')}>
        <PanelLeftOpen aria-hidden />
      </Button>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  // A per-browser preference; storage can be unavailable, and then the rail simply stays open.
  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(RAIL_KEY) === '1');
    } catch {}
  }, []);
  const setRail = (v: boolean) => {
    setCollapsed(v);
    try {
      window.localStorage.setItem(RAIL_KEY, v ? '1' : '0');
    } catch {}
  };
  const pathname = usePathname();
  useEffect(() => {
    setPendingHref(null);
  }, [pathname]);
  const isAssistant = pathname === '/assistant';
  const { t } = useT();

  return (
    <NavContext.Provider value={{ pendingHref, setPendingHref }}>
      {pendingHref && (
        <div className="fixed inset-x-0 top-0 z-50 h-0.5 overflow-hidden bg-primary/20 pointer-events-none" aria-hidden>
          <motion.div
            className="h-full bg-primary"
            initial={{ x: '-100%' }}
            animate={{ x: '100%' }}
            transition={{ repeat: Infinity, duration: 0.6, ease: 'linear' }}
          />
        </div>
      )}
      <div className={cn('min-h-dvh lg:grid', collapsed ? 'lg:grid-cols-[60px_1fr]' : 'lg:grid-cols-[232px_1fr]')}>
      <aside className={cn('sticky top-0 hidden h-dvh flex-col gap-6 overflow-y-auto border-r bg-background py-5 lg:flex', collapsed ? 'px-2' : 'px-3')}>
        {collapsed ? (
          <MiniRail onExpand={() => setRail(false)} />
        ) : (
          <>
            <div className="space-y-3">
              <div className="flex items-start justify-between gap-2">
                <Brand />
                <Button variant="ghost" size="icon" className="size-8 shrink-0 text-muted-foreground" onClick={() => setRail(true)} aria-label={t('rail.collapse')}>
                  <PanelLeftClose aria-hidden />
                </Button>
              </div>
              <DemoBadge />
            </div>
            <div className="flex-1">
              <NavLinks />
            </div>
            <RailFooter />
          </>
        )}
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
    </NavContext.Provider>
  );
}

