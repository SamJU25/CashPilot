'use client';

import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import {
  ArrowDownLeft,
  ArrowLeftRight,
  ArrowUpRight,
  Building2,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  EyeOff,
  Filter,
  Globe,
  KeyRound,
  Laptop,
  LayoutDashboard,
  Lock,
  Mail,
  MoreHorizontal,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  TriangleAlert,
  X,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { PageHeader, SectionTitle } from '@/components/common/bits';
import { ErrorState, LoadingBlock } from '@/components/common/states';
import { api, mailApi, type CurrencyConversionResult, type MailAccount, type MailAlert, type MailSettings, type MailState } from '@/lib/api';
import { NEW_ACCOUNT, POLL_MS, checkMail, clearMailError, disconnectMail, holdReason, mailDo, newAccountId, useMail } from '@/lib/bank-emails';
import { formatDate, formatMoney } from '@/lib/format';
import { useT, type Key } from '@/lib/i18n';
import { latestBalances, useCashChange } from '@/lib/use-cash-change';
import { useWorkspace } from '@/lib/workspace';
import { WORLD_CURRENCIES } from '@/lib/currencies';
import { spring } from '@/lib/motion';
import { cn } from '@/lib/utils';

/* ------------------------------------------------------------------ helpers */

function ago(ms: number, lang: string) {
  const s = Math.round((ms - Date.now()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: 'auto' });
  if (Math.abs(s) < 60) return rtf.format(s, 'second');
  if (Math.abs(s) < 3600) return rtf.format(Math.round(s / 60), 'minute');
  if (Math.abs(s) < 86400) return rtf.format(Math.round(s / 3600), 'hour');
  return rtf.format(Math.round(s / 86400), 'day');
}

/** Re-renders every second so countdowns and "checked 2 minutes ago" stay accurate. */
function useNow(every = 1_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), every);
    return () => window.clearInterval(id);
  }, [every]);
  return now;
}

const Tail = ({ tail }: { tail: string }) => <span className="font-mono text-[0.92em] tracking-tight">••{tail}</span>;

function Chip({ tone, children }: { tone: 'good' | 'warning' | 'critical' | 'muted' | 'info'; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium',
        tone === 'good' && 'bg-good/10 text-good-text',
        tone === 'warning' && 'bg-warning/15 text-warning-text',
        tone === 'critical' && 'bg-critical/10 text-critical-text',
        tone === 'muted' && 'bg-muted text-muted-foreground',
        tone === 'info' && 'bg-primary/10 text-primary',
      )}
    >
      {children}
    </span>
  );
}

const ERROR_KEY: Record<string, Key> = {
  auth_failed: 'be.err.auth',
  signin_expired: 'be.err.signinExpired',
  not_configured: 'be.err.notConfigured',
  unreachable: 'be.err.unreachable',
  tls_failed: 'be.err.tls',
  no_inbox: 'be.err.inbox',
  UNREACHABLE: 'be.err.server',
  TIMEOUT: 'be.err.server',
};

/* ------------------------------------------------------------------ privacy diagram */

/** Where the email goes: bank to the owner's own mailbox to this computer, and nowhere else. */
function PathDiagram() {
  const { t } = useT();
  const nodes = [
    { icon: Building2, label: t('be.path.bank') },
    { icon: Mail, label: t('be.path.mailbox') },
    { icon: Laptop, label: t('be.path.computer') },
  ];
  return (
    <div className="relative rounded-lg border bg-[linear-gradient(rgb(var(--primary)/0.06)_1px,transparent_1px),linear-gradient(90deg,rgb(var(--primary)/0.06)_1px,transparent_1px)] bg-[size:12px_12px] px-4 py-5">
      <ol className="flex items-start">
        {nodes.map(({ icon: Icon, label }, i) => (
          <Fragment key={i}>
            {i > 0 && (
              // Runs under the neighbouring cells' padding so it meets both icon boxes.
              <li aria-hidden className="relative -mx-[22px] mt-[18px] h-px min-w-6 flex-1 bg-primary/50">
                <span className="be-signal absolute -top-[2px] left-0 size-[5px] rounded-full bg-primary" style={{ animationDelay: `${i * 600}ms` }} />
              </li>
            )}
            <li className="relative z-10 flex w-20 shrink-0 flex-col items-center gap-2 text-center">
              <span className={cn('grid size-9 place-items-center rounded-lg border bg-card', i === 2 && 'border-primary text-primary')}>
                <Icon className="size-4" aria-hidden />
              </span>
              <span className="text-[11px] leading-tight text-ink-2">{label}</span>
            </li>
          </Fragment>
        ))}
      </ol>
      <p className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-muted-foreground">
        <X className="size-3" aria-hidden />
        {t('be.path.noServer')}
      </p>
    </div>
  );
}

function Promises() {
  const { t } = useT();
  const items: [typeof Lock, Key, Key][] = [
    [EyeOff, 'be.p.readonly', 'be.p.readonlyBody'],
    [ShieldCheck, 'be.p.senders', 'be.p.sendersBody'],
    [KeyRound, 'be.p.password', 'be.p.passwordBody'],
    [Lock, 'be.p.ai', 'be.p.aiBody'],
  ];
  return (
    <ul className="space-y-3.5">
      {items.map(([Icon, title, body]) => (
        <li key={title} className="flex gap-3">
          <Icon className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
          <div>
            <p className="text-sm font-medium">{t(title)}</p>
            <p className="text-[13px] leading-relaxed text-muted-foreground">{t(body)}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ connect */

// Mail hosts with step-by-step help for their app password or authorization code.
const HOW_KEY: Record<string, Key> = {
  'imap.gmail.com': 'be.how.gmail',
  'imap.qq.com': 'be.how.qq',
  'imap.163.com': 'be.how.163',
  'imap.mail.me.com': 'be.how.icloud',
};

const OAUTH_LABEL = { google: 'Google', microsoft: 'Microsoft' } as const;
const SIGNIN_WAIT_MS = 10 * 60_000;

/** Opens the provider's sign-in page and waits for the backend to report the mailbox connected. */
async function signInInBrowser(body: { address: string; host: string; username: string; name: string }): Promise<'connected' | 'timeout'> {
  // Opened inside the click so popup blockers allow it; pointed at the provider once the URL is known.
  const tab = window.open('', '_blank');
  try {
    const { url } = await mailApi.oauthStart({ ...body, return_to: window.location.origin + window.location.pathname });
    if (tab) {
      tab.opener = null;
      tab.location.href = url;
    } else {
      window.location.assign(url);
    }
  } catch (e) {
    tab?.close();
    throw e;
  }
  const until = Date.now() + SIGNIN_WAIT_MS;
  while (Date.now() < until) {
    await new Promise((r) => setTimeout(r, 1500));
    const state = await mailApi.state().catch(() => null);
    const conns = state?.connections || (state?.connection ? [state.connection] : []);
    const match = conns.find((c) => c.address.toLowerCase() === body.address.toLowerCase());
    if (state && match) {
      await mailDo(async () => state);
      return 'connected';
    }
  }
  return 'timeout';
}

type Stage = 'email' | 'password' | 'waiting' | 'success';

/** A form field with its label floating above the value, as mail sign-in pages draw it. */
function Field({
  id,
  label,
  invalid,
  describedBy,
  children,
}: {
  id: string;
  label: string;
  invalid?: boolean;
  describedBy?: string;
  children: (props: { id: string; 'aria-invalid'?: boolean; 'aria-describedby'?: string; className: string; placeholder: string }) => React.ReactNode;
}) {
  return (
    <div className="group relative">
      {children({
        id,
        'aria-invalid': invalid || undefined,
        'aria-describedby': describedBy,
        placeholder: ' ',
        className: cn(
          'peer h-14 w-full rounded-lg border bg-background px-3.5 pb-2 pt-6 text-[15px] outline-none transition-colors',
          'focus:border-primary focus:ring-1 focus:ring-primary',
          invalid && 'border-critical focus:border-critical focus:ring-critical',
        ),
      })}
      <label
        htmlFor={id}
        className={cn(
          'pointer-events-none absolute left-3.5 top-2 text-[11px] font-medium text-muted-foreground transition-all',
          'peer-placeholder-shown:top-[1.05rem] peer-placeholder-shown:text-[15px] peer-placeholder-shown:font-normal',
          'peer-focus:top-2 peer-focus:text-[11px] peer-focus:font-medium peer-focus:text-primary',
          invalid && 'text-critical-text peer-focus:text-critical-text',
        )}
      >
        {label}
      </label>
    </div>
  );
}

function Connect({ onDone }: { onDone?: () => void } = {}) {
  const { t } = useT();
  const reduce = useReducedMotion();
  const [stage, setStage] = useState<Stage>('email');
  const [address, setAddress] = useState('');
  const [secret, setSecret] = useState('');
  const [show, setShow] = useState(false);
  const [settings, setSettings] = useState<MailSettings | null>(null);
  const [manual, setManual] = useState(false);
  const [server, setServer] = useState({ host: '', username: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Key | null>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);

  const trimmed = address.trim();
  const domain = trimmed.split('@')[1] ?? '';
  const valid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(trimmed);
  const oauth = settings?.oauth && !manual ? settings.oauth : null;
  const blocked = !!settings?.oauth_only && !settings.oauth && !manual;
  const host = server.host.trim().toLowerCase();
  const kind = manual || !settings ? (/\.(qq|163)\.com$/.test(host) ? 'auth_code' : 'password') : settings.secret_kind;
  const secretLabel = kind === 'auth_code' ? t('be.authCode') : kind === 'app_password' ? t('be.appPassword') : t('be.password');

  // Step 1: find how to reach this mailbox, then move on to the password.
  const next = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) {
      setError('be.si.invalidEmail');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { settings: found } = await mailApi.discover(trimmed);
      setSettings(found);
      setServer(found ? { host: found.host, username: found.username } : { host: `imap.${domain}`, username: trimmed });
      setManual(!found);
      setStage('password');
    } catch {
      setError('be.err.server');
    } finally {
      setBusy(false);
    }
  };

  // Step 2: test the password against the server; only a working one is saved.
  const signIn = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!secret) return;
    setBusy(true);
    setError(null);
    try {
      const state = await mailApi.connect({ address: trimmed, secret, host, port: 993, username: server.username.trim(), name: !manual && settings ? settings.name : host });
      await mailDo(async () => state);
      onDone?.();
    } catch (x) {
      setError(ERROR_KEY[(x as { code?: string }).code ?? ''] ?? 'be.err.generic');
      passwordRef.current?.select();
    } finally {
      setBusy(false);
    }
  };

  const checkNow = async () => {
    const st = await mailApi.state().catch(() => null);
    const conns = st?.connections || (st?.connection ? [st.connection] : []);
    if (st && conns.some((c) => c.address.toLowerCase() === trimmed.toLowerCase())) {
      await mailDo(async () => st);
      setStage('success');
      setTimeout(() => {
        onDone?.();
        void checkMail();
      }, 1200);
    }
  };

  const browserSignIn = async () => {
    if (!oauth) return;
    setError(null);
    setStage('waiting');
    try {
      const r = await signInInBrowser({ address: trimmed, host, username: server.username.trim(), name: settings!.name });
      if (r === 'timeout') {
        setError('be.err.signinTimeout');
        setStage('password');
      } else if (r === 'connected') {
        setStage('success');
        setTimeout(() => {
          onDone?.();
          void checkMail();
        }, 1200);
      }
    } catch (x) {
      setError(ERROR_KEY[(x as { code?: string }).code ?? ''] ?? 'be.err.generic');
      setStage('password');
    }
  };

  const back = () => {
    setStage('email');
    setSecret('');
    setError(null);
    setShow(false);
  };

  const slide = reduce ? {} : { initial: { opacity: 0, x: 12 }, animate: { opacity: 1, x: 0 }, exit: { opacity: 0, x: -12 }, transition: spring.snappy };

  return (
    <div className={cn(onDone ? 'w-full' : 'grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start')}>
      <div className={cn('mx-auto w-full max-w-[440px] rounded-2xl border bg-card px-6 py-8 shadow-sm sm:px-9 sm:py-10', onDone && 'border-0 bg-transparent px-2 py-2 shadow-none sm:px-4 sm:py-4')}>
        <div className="mb-7 text-center">
          <span className="mx-auto mb-4 grid size-12 place-items-center rounded-2xl bg-primary/10 text-primary ring-1 ring-primary/20">
            <Mail className="size-6" aria-hidden />
          </span>
          <h2 className="font-display text-2xl font-semibold tracking-tight">{stage === 'email' ? t('be.si.title') : t('be.si.welcome')}</h2>
          {stage === 'email' ? (
            <p className="mt-1.5 text-sm text-muted-foreground">{t('be.si.sub')}</p>
          ) : (
            <button
              type="button"
              onClick={back}
              className="mx-auto mt-3 flex max-w-full items-center gap-2 rounded-full border py-1 pl-1 pr-3 text-sm transition-colors hover:bg-muted"
              aria-label={t('be.si.change', { address: trimmed })}
            >
              <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary text-[11px] font-semibold uppercase text-primary-foreground">{trimmed[0]}</span>
              <span className="truncate">{trimmed}</span>
              <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
            </button>
          )}
        </div>

        <AnimatePresence mode="wait" initial={false}>
          {stage === 'email' && (
            <motion.form key="email" {...slide} onSubmit={next} noValidate className="space-y-5">
              <div>
                <Field id="be-address" label={t('be.si.email')} invalid={!!error} describedBy={error ? 'be-email-error' : undefined}>
                  {(p) => (
                    <input
                      {...p}
                      ref={emailRef}
                      autoFocus
                      type="email"
                      inputMode="email"
                      autoComplete="username"
                      autoCapitalize="off"
                      spellCheck={false}
                      value={address}
                      onChange={(e) => {
                        setAddress(e.target.value);
                        setError(null);
                      }}
                    />
                  )}
                </Field>
                {error && (
                  <p id="be-email-error" role="alert" className="mt-2 flex items-start gap-1.5 text-[13px] text-critical-text">
                    <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                    {t(error)}
                  </p>
                )}
              </div>
              <p className="text-[13px] leading-relaxed text-muted-foreground">{t('be.si.worksWith')}</p>
              <Button type="submit" size="lg" className="h-11 w-full text-[15px]" disabled={busy || !trimmed}>
                {busy ? <RefreshCw className="animate-spin" aria-hidden /> : null}
                {busy ? t('be.si.checking') : t('be.si.next')}
              </Button>
              <details className="group rounded-lg bg-muted/50 px-3.5 py-3 text-[13px]">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-2 font-medium text-ink-2">
                  {t('be.si.why')}
                  <ChevronDown className="size-4 transition-transform group-open:rotate-180" aria-hidden />
                </summary>
                <p className="mt-2 leading-relaxed text-muted-foreground">{t('be.s1Body')}</p>
              </details>
            </motion.form>
          )}

          {stage === 'password' && (
            <motion.form key="password" {...slide} onSubmit={signIn} noValidate className="space-y-5">
              {/* Lets password managers file the password under the right address. */}
              <input type="email" name="username" autoComplete="username" value={trimmed} readOnly hidden />

              {settings && !manual && (
                <p className={cn('flex items-center justify-center gap-1.5 text-[13px]', blocked ? 'text-warning-text' : 'text-muted-foreground')}>
                  {blocked ? <TriangleAlert className="size-3.5" aria-hidden /> : <Check className="size-3.5 text-good-text" aria-hidden />}
                  {settings.name}
                  <span aria-hidden>·</span>
                  {settings.verifies_sender ? t('be.checksSender') : t('be.youConfirm')}
                </p>
              )}

              {blocked ? (
                <div className="space-y-4">
                  <p className="rounded-lg border border-warning/40 bg-warning/5 p-3.5 text-[13px] leading-relaxed text-warning-text">{t('be.oauthOnly', { name: settings!.name })}</p>
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full text-[13px]"
                    onClick={() => {
                      setManual(true);
                    }}
                  >
                    <KeyRound className="mr-1.5 size-4" aria-hidden />
                    {t('be.usePasswordInstead')}
                  </Button>
                </div>
              ) : oauth ? (
                <div className="space-y-4">
                  <Button type="button" size="lg" variant="outline" className="h-11 w-full gap-2.5 text-[15px]" onClick={browserSignIn}>
                    <ProviderMark provider={oauth} />
                    {t('be.signInWith', { provider: OAUTH_LABEL[oauth] })}
                  </Button>
                  <p className="text-center text-[12.5px] leading-relaxed text-muted-foreground">{t('be.browserBody', { provider: OAUTH_LABEL[oauth] })}</p>
                </div>
              ) : (
                <>
                  {!settings && <p className="text-center text-[13px] leading-relaxed text-muted-foreground">{t('be.notFound', { domain })}</p>}
                  <div>
                    <div className="relative">
                      <Field id="be-secret" label={secretLabel} invalid={!!error} describedBy={cn('be-secret-help', error && 'be-secret-error')}>
                        {(p) => (
                          <input
                            {...p}
                            ref={passwordRef}
                            autoFocus
                            className={cn(p.className, 'pr-16')}
                            type={show ? 'text' : 'password'}
                            autoComplete="current-password"
                            autoCapitalize="off"
                            spellCheck={false}
                            value={secret}
                            onChange={(e) => {
                              setSecret(e.target.value);
                              setError(null);
                            }}
                          />
                        )}
                      </Field>
                      <button
                        type="button"
                        onClick={() => setShow((s) => !s)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md px-2 py-1 text-xs font-medium text-ink-2 hover:bg-muted hover:text-foreground"
                        aria-pressed={show}
                        aria-controls="be-secret"
                      >
                        {show ? t('be.si.hide') : t('be.si.show')}
                      </button>
                    </div>
                    {error && (
                      <p id="be-secret-error" role="alert" className="mt-2 flex items-start gap-1.5 text-[13px] text-critical-text">
                        <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                        {t(error)}
                      </p>
                    )}
                    <p id="be-secret-help" className="mt-2 text-[12.5px] leading-relaxed text-muted-foreground">
                      {t(HOW_KEY[host] ?? 'be.how.generic')}
                    </p>
                  </div>
                  <Button type="submit" size="lg" className="h-11 w-full text-[15px]" disabled={busy || !secret || !host}>
                    {busy ? <RefreshCw className="animate-spin" aria-hidden /> : null}
                    {busy ? t('be.si.signingIn') : t('be.si.signIn')}
                  </Button>
                </>
              )}

              {/* Server details only matter for the rare mailbox discovery cannot place. */}
              <div className="border-t pt-4">
                <button
                  type="button"
                  aria-expanded={manual}
                  onClick={() => setManual((m) => !m)}
                  className="flex w-full items-center justify-between text-xs text-muted-foreground hover:text-foreground"
                >
                  {t('be.advanced')}
                  <ChevronDown className={cn('size-3.5 transition-transform', manual && 'rotate-180')} aria-hidden />
                </button>
                {manual && (
                  <div className="mt-3 space-y-2.5">
                    <div className="grid gap-1">
                      <Label htmlFor="be-host" className="text-xs">{t('be.host')}</Label>
                      <Input id="be-host" value={server.host} onChange={(e) => setServer({ ...server, host: e.target.value })} className="h-9 font-mono text-xs" />
                    </div>
                    <div className="grid gap-1">
                      <Label htmlFor="be-user" className="text-xs">{t('be.username')}</Label>
                      <Input id="be-user" value={server.username} onChange={(e) => setServer({ ...server, username: e.target.value })} className="h-9 font-mono text-xs" />
                    </div>
                    <p className="text-[11px] text-muted-foreground">{t('be.tlsOnly')}</p>
                  </div>
                )}
              </div>
            </motion.form>
          )}

          {stage === 'waiting' && oauth && (
            <motion.div key="waiting" {...slide} className="space-y-5 text-center" aria-live="polite">
              <span className="relative mx-auto grid size-14 place-items-center">
                <span className="absolute inset-0 animate-ping rounded-full bg-primary/15 motion-reduce:hidden" aria-hidden />
                <span className="relative grid size-14 place-items-center rounded-full border bg-background">
                  <ProviderMark provider={oauth} />
                </span>
              </span>
              <div>
                <p className="font-medium">{t('be.waitingSignin', { provider: OAUTH_LABEL[oauth] })}</p>
                <p className="mt-1 text-sm text-muted-foreground">{t('be.waitingBody')}</p>
              </div>
              <div className="flex flex-col gap-2">
                <Button type="button" size="sm" onClick={checkNow} className="gap-2">
                  <Check className="size-4" />
                  I have finished sign-in
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => setStage('password')}>
                  {t('be.si.cancel')}
                </Button>
              </div>
            </motion.div>
          )}

          {stage === 'success' && (
            <motion.div key="success" {...slide} className="space-y-4 py-3 text-center" aria-live="polite">
              <span className="mx-auto grid size-14 place-items-center rounded-full bg-good/15 text-good-text ring-1 ring-good/30">
                <Check className="size-7" />
              </span>
              <div>
                <p className="font-semibold text-base text-foreground">Connected to {trimmed}!</p>
                <p className="mt-1 text-xs text-muted-foreground">Syncing transaction alerts and debit notifications...</p>
              </div>
              <div className="flex justify-center pt-2">
                <RefreshCw className="size-5 animate-spin text-muted-foreground" />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <p className="mt-7 flex items-center justify-center gap-1.5 text-center text-xs text-muted-foreground">
          <Lock className="size-3 shrink-0" aria-hidden />
          {t('be.si.readOnly')}
        </p>
      </div>

      {!onDone && (
        <aside className="space-y-5 rounded-xl border bg-card p-5">
          <h2 className="font-display text-base font-semibold tracking-tight">{t('be.privacyTitle')}</h2>
          <PathDiagram />
          <Promises />
        </aside>
      )}
    </div>
  );
}

/** The provider's own mark, drawn small and in its colours, as sign-in buttons conventionally show it. */
function ProviderMark({ provider }: { provider: 'google' | 'microsoft' }) {
  if (provider === 'microsoft')
    return (
      <svg viewBox="0 0 16 16" className="size-4" aria-hidden>
        <rect x="1" y="1" width="6.5" height="6.5" fill="#f25022" />
        <rect x="8.5" y="1" width="6.5" height="6.5" fill="#7fba00" />
        <rect x="1" y="8.5" width="6.5" height="6.5" fill="#00a4ef" />
        <rect x="8.5" y="8.5" width="6.5" height="6.5" fill="#ffb900" />
      </svg>
    );
  return (
    <span className="grid size-5 place-items-center rounded-full bg-white" aria-hidden>
      <svg viewBox="0 0 18 18" className="size-3.5">
        <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z" />
        <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z" />
        <path fill="#FBBC05" d="M3.97 10.72A5.4 5.4 0 0 1 3.68 9c0-.6.1-1.18.29-1.72V4.95H.96A9 9 0 0 0 0 9c0 1.45.35 2.83.96 4.05l3.01-2.33z" />
        <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z" />
      </svg>
    </span>
  );
}

/* ------------------------------------------------------------------ connected: status */

function StatusStrip({ state }: { state: MailState }) {
  const { t, lang } = useT();
  const mail = useMail();
  const now = useNow();
  const [addingMailbox, setAddingMailbox] = useState(false);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const conn = state.connection!;
  const connections = state.connections && state.connections.length > 0 ? state.connections : [conn];
  const failingConn = connections.find((c) => !!c.last_error);
  const failing = !!failingConn;
  const checked = mail.checkedAt ?? (conn.last_sync ? Date.parse(conn.last_sync) : null);
  const nextIn = checked ? Math.max(0, Math.round((checked + POLL_MS - now) / 1000)) : null;

  const handleDisconnect = async (address?: string) => {
    setDisconnecting(address ?? 'all');
    try {
      await disconnectMail(address);
    } finally {
      setDisconnecting(null);
    }
  };

  return (
    <div className="space-y-2.5">
      <div
        className={cn(
          'flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl border px-5 py-4',
          failing ? 'border-critical/40 bg-critical/5' : 'bg-card',
        )}
      >
        <div className="flex min-w-0 items-center gap-3">
          <span className="relative grid size-2.5 place-items-center" aria-hidden>
            {!failing && <span className="absolute inset-0 animate-ping rounded-full bg-good/60 motion-reduce:hidden" />}
            <span className={cn('relative size-2.5 rounded-full', failing ? 'bg-critical' : 'bg-good')} />
          </span>
          <div className="min-w-0">
            <p className={cn('text-sm font-medium', !failing && 'truncate')}>
              {failing
                ? `${connections.length > 1 ? failingConn!.address + ': ' : ''}${t(ERROR_KEY[failingConn!.last_error!] ?? 'be.err.generic')}`
                : t('be.watching', { address: conn.address })}
            </p>
            <p className="text-xs text-muted-foreground">
              {checked ? t('be.checked', { when: ago(checked, lang) }) : t('be.neverChecked')}
              {!failing && nextIn !== null && <span className="figures"> · {t('be.nextIn', { s: nextIn })}</span>}
            </p>
          </div>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {conn.oauth && conn.last_error === 'signin_expired' && (
            <Button size="sm" onClick={() => signInInBrowser({ address: conn.address, host: conn.host, username: conn.username, name: conn.name }).catch(() => {})}>
              <ProviderMark provider={conn.oauth} />
              {t('be.signInAgain')}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={checkMail} disabled={mail.syncing}>
            <RefreshCw className={cn(mail.syncing && 'animate-spin')} aria-hidden />
            {t('be.checkNow')}
          </Button>

          {/* Add Another Mailbox Dialog */}
          <Dialog open={addingMailbox} onOpenChange={setAddingMailbox}>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm" className="gap-1.5">
                <Plus className="size-3.5" aria-hidden />
                Add Mailbox
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-xl">
              <DialogHeader>
                <DialogTitle>Connect another mailbox</DialogTitle>
                <DialogDescription>
                  Monitor multiple company inboxes simultaneously. Transactions from all connected accounts will feed directly into your live cash view.
                </DialogDescription>
              </DialogHeader>
              <div className="pt-2">
                <Connect onDone={() => setAddingMailbox(false)} />
              </div>
            </DialogContent>
          </Dialog>

          <Dialog>
            <DialogTrigger asChild>
              <Button variant="ghost" size="sm" className="text-muted-foreground" disabled={!!disconnecting}>
                {disconnecting === 'all' ? <RefreshCw className="mr-1.5 size-3.5 animate-spin" /> : null}
                {t('be.disconnect')}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{t('be.disconnectTitle')}</DialogTitle>
                <DialogDescription>{t('be.disconnectBody', { address: conn.address })}</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="outline">{t('be.keep')}</Button>
                </DialogClose>
                <DialogClose asChild>
                  <Button
                    variant="destructive"
                    disabled={!!disconnecting}
                    onClick={() => handleDisconnect()}
                  >
                    {disconnecting === 'all' ? <RefreshCw className="mr-1.5 size-3.5 animate-spin" /> : null}
                    {t('be.disconnect')}
                  </Button>
                </DialogClose>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Multiple connected inboxes bar */}
      {connections.length > 1 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-muted/20 px-4 py-2.5 text-xs">
          <span className="font-medium text-muted-foreground">Connected Inboxes ({connections.length}):</span>
          {connections.map((c) => (
            <div
              key={c.address}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-ink-1 shadow-2xs transition-colors',
                c.last_error ? 'border-critical/40 bg-critical/10 text-critical-text' : 'bg-card',
              )}
            >
              <span className={cn('size-1.5 rounded-full', c.last_error ? 'bg-critical' : 'bg-good')} />
              <span className="font-mono text-[11px]">{c.address}</span>
              {c.last_error && <span className="text-[10px] uppercase font-semibold">({c.last_error})</span>}
              {c.oauth && c.last_error === 'signin_expired' && (
                <button
                  type="button"
                  onClick={() => signInInBrowser({ address: c.address, host: c.host, username: c.username, name: c.name }).catch(() => {})}
                  className="ml-1 rounded bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
                >
                  {t('be.signInAgain')}
                </button>
              )}
              <button
                type="button"
                disabled={!!disconnecting}
                onClick={() => handleDisconnect(c.address)}
                className="ml-1 text-muted-foreground hover:text-critical-text disabled:opacity-50"
                title={`Disconnect ${c.address}`}
                aria-label={`Disconnect ${c.address}`}
              >
                {disconnecting === c.address ? <RefreshCw className="size-3 animate-spin" /> : <X className="size-3" />}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ accounts */

function AccountCard({ acc, targets }: { acc: MailAccount; targets: { id: string; name: string }[] }) {
  const { t } = useT();
  const [target, setTarget] = useState<string>(acc.target ?? targets[0]?.id ?? NEW_ACCOUNT);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const pending = acc.status === 'pending' || editing;
  const name = acc.target === NEW_ACCOUNT ? newAccountId(acc) : targets.find((x) => x.id === acc.target)?.name ?? acc.target;

  const save = async (status: MailAccount['status'], customTarget?: string) => {
    setSaving(true);
    try {
      await mailDo(() => mailApi.decideAccount(acc.key, status, status === 'use' ? (customTarget ?? target) : undefined));
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <li
      className={cn(
        'flex flex-col rounded-xl border p-4 transition-colors',
        pending ? 'border-warning/50 bg-warning/5' : acc.status === 'ignore' ? 'bg-muted/30' : 'bg-card',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {pending && <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-warning-text">{t('be.newFound')}</p>}
          <p className="truncate font-medium">
            {acc.bank} <Tail tail={acc.tail} />
          </p>
          <p className="text-xs text-muted-foreground">{t('be.accMeta', { currency: acc.currency, n: acc.alerts })}</p>
        </div>
        <div className="text-right">
          <p className="figures font-display text-lg font-semibold leading-tight">{acc.balance ? formatMoney(acc.balance, acc.currency) : '—'}</p>
          <p className="text-[11px] text-muted-foreground">{t('be.bankSays')}</p>
        </div>
      </div>

      {pending ? (
        <div className="mt-4 space-y-3 border-t border-warning/30 pt-3">
          <p className="text-sm">{t('be.isYours')}</p>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={target} onValueChange={setTarget}>
              <SelectTrigger className="h-9 w-56" aria-label={t('be.linkTo')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {targets.map((x) => (
                  <SelectItem key={x.id} value={x.id}>
                    {t('be.countAs', { name: x.name })}
                  </SelectItem>
                ))}
                <SelectItem value={NEW_ACCOUNT}>{t('be.addNew', { name: newAccountId(acc) })}</SelectItem>
              </SelectContent>
            </Select>
            <Button size="sm" disabled={saving} onClick={() => save('use')}>
              {saving ? <RefreshCw className="size-3.5 animate-spin" /> : <Check aria-hidden />}
              {t('be.useIt')}
            </Button>
            {target !== NEW_ACCOUNT && (
              <Button
                size="sm"
                variant="outline"
                disabled={saving}
                onClick={() => {
                  setTarget(NEW_ACCOUNT);
                  void save('use', NEW_ACCOUNT);
                }}
              >
                Track as New
              </Button>
            )}
            <Button size="sm" variant="ghost" disabled={saving} onClick={() => save('ignore')}>
              {t('be.notMine')}
            </Button>
            {editing && acc.status !== 'pending' && (
              <Button size="sm" variant="ghost" disabled={saving} onClick={() => setEditing(false)}>
                {t('common.cancel')}
              </Button>
            )}
          </div>
        </div>
      ) : (
        <div className="mt-3 flex items-center justify-between gap-2 border-t pt-3 text-sm">
          {acc.status === 'use' ? (
            <span className="flex min-w-0 items-center gap-1.5 text-ink-2">
              <Check className="size-3.5 shrink-0 text-good-text" aria-hidden />
              <span className="truncate">{t('be.countedAs', { name: name ?? '' })}</span>
            </span>
          ) : (
            <span className="text-muted-foreground">{t('be.ignored')}</span>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="size-8" aria-label={t('be.accountMenu')}>
                <MoreHorizontal aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => setEditing(true)}>{t('be.changeLink')}</DropdownMenuItem>
              {acc.status === 'use' ? (
                <DropdownMenuItem onSelect={() => save('ignore')}>{t('be.stopUsing')}</DropdownMenuItem>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}
    </li>
  );
}

/* ------------------------------------------------------------------ review */

const REVIEW_KEY: Record<NonNullable<MailAlert['review']>, Key> = {
  unlisted_bank: 'be.r.unlisted',
  unverified_sender: 'be.r.unverified',
  no_account: 'be.r.noAccount',
  no_direction: 'be.r.noDirection',
};

function ReviewList({ alerts }: { alerts: MailAlert[] }) {
  const { t } = useT();
  const [actioningId, setActioningId] = useState<string | null>(null);
  if (alerts.length === 0) return null;

  const handleAlert = async (id: string, action: 'accept' | 'dismiss' | 'trust') => {
    setActioningId(`${id}:${action}`);
    try {
      await mailDo(() => mailApi.decideAlert(id, action));
    } finally {
      setActioningId(null);
    }
  };

  return (
    <section>
      <SectionTitle aside={t('be.reviewAside')}>{t('be.review')}</SectionTitle>
      <ul className="divide-y rounded-xl border bg-card">
        {alerts.map((a) => {
          const isBusy = !!actioningId && actioningId.startsWith(`${a.id}:`);
          return (
            <li key={a.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
              <TriangleAlert className="size-4 shrink-0 text-warning-text" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{t(a.review ? REVIEW_KEY[a.review] : 'be.r.noAccount', { bank: a.bank })}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {a.bank} {a.account_tail && <Tail tail={a.account_tail} />} · {formatDate(a.occurred_on)} · {a.counterparty ?? '—'}
                </p>
              </div>
              <span className={cn('figures text-sm font-medium', a.direction === 'IN' && 'text-good-text')}>
                {a.direction === 'IN' ? '+' : '−'}
                {formatMoney(a.amount, a.currency)}
              </span>
              <div className="flex gap-1.5">
                {(a.review === 'unverified_sender' || a.review === 'unlisted_bank') && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={isBusy}
                    onClick={() => handleAlert(a.id, 'trust')}
                  >
                    {actioningId === `${a.id}:trust` ? <RefreshCw className="mr-1.5 size-3 animate-spin" /> : null}
                    {t('be.trustBank', { bank: a.bank })}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  disabled={isBusy}
                  onClick={() => handleAlert(a.id, 'accept')}
                >
                  {actioningId === `${a.id}:accept` ? <RefreshCw className="mr-1.5 size-3 animate-spin" /> : null}
                  {t('be.countIt')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={isBusy}
                  onClick={() => handleAlert(a.id, 'dismiss')}
                >
                  {actioningId === `${a.id}:dismiss` ? <RefreshCw className="mr-1.5 size-3 animate-spin" /> : null}
                  {t('be.dismiss')}
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/* ------------------------------------------------------------------ feed */

function Feed({ alerts, address, accounts }: { alerts: MailAlert[]; address: string; accounts: MailAccount[] }) {
  const { t } = useT();
  const { live, source, hasData } = useWorkspace();
  const apply = useCashChange();
  const reduce = useReducedMotion();

  // Filters & Search
  const [query, setQuery] = useState('');
  const [directionFilter, setDirectionFilter] = useState<'all' | 'IN' | 'OUT' | 'transfer'>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'counted' | 'waiting' | 'ignored'>('all');
  const [page, setPage] = useState(1);
  const pageSize = 20;

  // Editing state for counterparty / note
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editCounterparty, setEditCounterparty] = useState('');
  const [editNote, setEditNote] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);

  // Cross-currency alert conversion state
  const [convertingAlert, setConvertingAlert] = useState<MailAlert | null>(null);
  const [conversionQuote, setConversionQuote] = useState<CurrencyConversionResult | null>(null);
  const [conversionLoading, setConversionLoading] = useState(false);
  const [conversionError, setConversionError] = useState<string | null>(null);
  const [convertingApplying, setConvertingApplying] = useState(false);

  const startConvert = async (a: MailAlert) => {
    if (!ctx.currency) return;
    setConvertingAlert(a);
    setConversionQuote(null);
    setConversionLoading(true);
    setConversionError(null);
    try {
      const res = await api.convertCurrency({
        amount: a.amount,
        from_currency: a.currency,
        to_currency: ctx.currency,
      });
      setConversionQuote(res);
    } catch (err) {
      setConversionError(err instanceof Error ? err.message : String(err));
    } finally {
      setConversionLoading(false);
    }
  };

  const applyConversion = async () => {
    if (!convertingAlert || !conversionQuote || !ctx.currency) return;
    setConvertingApplying(true);
    try {
      const a = convertingAlert;
      const acc = accounts.find((x) => x.bank_domain === a.bank_domain && x.tail === a.account_tail && x.currency === a.currency);
      const targetId = acc?.target && acc.target !== NEW_ACCOUNT ? acc.target : newAccountId(acc ?? { bank: a.bank, tail: a.account_tail });
      const known = latestBalances(analysis).some((b) => b.id === targetId);
      const description = `${a.counterparty || targetId} (${a.amount} ${a.currency} @ ${conversionQuote.spot_exchange_rate})`;
      const change = !known && a.balance_after
        ? { mode: 'SET_BALANCE' as const, amount: conversionQuote.net_converted_amount, description }
        : { mode: a.direction === 'IN' ? ('INFLOW' as const) : ('OUTFLOW' as const), amount: conversionQuote.net_converted_amount, description };

      await apply({
        ...change,
        accountId: targetId,
        effectiveDate: a.occurred_on,
        alertId: a.id,
        transfer: !!a.transfer_with,
        currency: ctx.currency,
      });
      setConvertingAlert(null);
      setConversionQuote(null);
    } catch (err) {
      setConversionError(err instanceof Error ? err.message : String(err));
    } finally {
      setConvertingApplying(false);
    }
  };

  // Newest alert per account (alerts arrive newest first).
  const latest = new Map<string, string>();
  for (const a of alerts) {
    if (a.status !== 'dismissed') {
      const k = `${a.bank_domain}|${a.account_tail}|${a.currency}`;
      if (!latest.has(k)) latest.set(k, a.id);
    }
  }
  const useBankBalance = (a: MailAlert) => {
    const acc = accounts.find((x) => x.bank_domain === a.bank_domain && x.tail === a.account_tail && x.currency === a.currency);
    if (!acc?.target) return;
    apply({
      mode: 'SET_BALANCE',
      amount: a.balance_after!,
      accountId: acc.target === NEW_ACCOUNT ? newAccountId(acc) : acc.target,
      description: t('be.openingFrom', { bank: newAccountId(acc) }),
      effectiveDate: a.occurred_on,
      currency: a.currency,
    }).catch(() => {});
  };
  const analysis = source === 'live' ? live.analysis : undefined;
  const ctx = {
    sample: hasData && source !== 'live',
    currency: analysis?.currency,
    statementEnd: analysis && analysis.document_format !== 'MANUAL' ? analysis.end_date ?? undefined : undefined,
  };
  const counted = new Set((live.entries ?? []).map((e) => e.alertId).filter(Boolean));
  const baseShown = alerts.filter((a) => a.status !== 'dismissed' && a.status !== 'review');

  const startEdit = (a: MailAlert) => {
    setEditingId(a.id);
    setEditCounterparty(a.counterparty || '');
    setEditNote(a.note || '');
  };

  const cancelEdit = () => {
    setEditingId(null);
  };

  const saveEdit = async (alertId: string) => {
    setSavingEdit(true);
    await mailDo(() => mailApi.editAlert(alertId, { counterparty: editCounterparty, note: editNote }));
    setSavingEdit(false);
    setEditingId(null);
  };

  // Filter application
  const filtered = baseShown.filter((a) => {
    if (directionFilter === 'transfer' && !a.transfer_with) return false;
    if (directionFilter === 'IN' && (a.direction !== 'IN' || a.transfer_with)) return false;
    if (directionFilter === 'OUT' && (a.direction !== 'OUT' || a.transfer_with)) return false;

    if (statusFilter === 'counted' && !counted.has(a.id)) return false;
    if (statusFilter === 'waiting' && a.status !== 'waiting') return false;
    if (statusFilter === 'ignored' && a.status !== 'ignored') return false;

    if (query.trim()) {
      const q = query.toLowerCase().trim();
      const matchParty = (a.counterparty ?? '').toLowerCase().includes(q);
      const matchBank = a.bank.toLowerCase().includes(q);
      const matchTail = a.account_tail.toLowerCase().includes(q);
      const matchAmount = a.amount.includes(q);
      const matchDate = a.occurred_on.includes(q);
      const matchNote = (a.note ?? '').toLowerCase().includes(q);
      if (!matchParty && !matchBank && !matchTail && !matchAmount && !matchDate && !matchNote) {
        return false;
      }
    }
    return true;
  });

  // Reset page when filtering
  useEffect(() => {
    setPage(1);
  }, [query, directionFilter, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pagedAlerts = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  const state = (a: MailAlert): [string, 'good' | 'warning' | 'muted' | 'info'] => {
    if (counted.has(a.id)) return [t('be.st.counted'), 'good'];
    if (a.status === 'waiting') return [t('be.st.waiting'), 'warning'];
    if (a.status === 'ignored') return [t('be.st.ignored'), 'muted'];
    const hold = holdReason(a, ctx);
    if (hold) return [t(`be.st.${hold}` as Key), 'muted'];
    return [t('be.st.counting'), 'info'];
  };

  const hasActiveFilters = query.trim() !== '' || directionFilter !== 'all' || statusFilter !== 'all';
  const resetFilters = () => {
    setQuery('');
    setDirectionFilter('all');
    setStatusFilter('all');
    setPage(1);
  };

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SectionTitle aside={t('be.feedAside')}>{t('be.feed')}</SectionTitle>

        {/* Search & Filter Toolbar */}
        {baseShown.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            {/* Search Input */}
            <div className="relative min-w-[190px] flex-1 sm:w-56 sm:flex-initial">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search merchant, bank..."
                className="h-8 pl-8 pr-7 text-xs bg-card"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label="Clear search"
                >
                  <X className="size-3" />
                </button>
              )}
            </div>

            {/* Direction Filter Tabs */}
            <div className="flex items-center rounded-lg border bg-muted/30 p-0.5 text-[11px]">
              <button
                type="button"
                onClick={() => setDirectionFilter('all')}
                className={cn('rounded px-2 py-1 font-medium transition-colors', directionFilter === 'all' ? 'bg-card text-foreground shadow-2xs' : 'text-muted-foreground hover:text-foreground')}
              >
                All
              </button>
              <button
                type="button"
                onClick={() => setDirectionFilter('IN')}
                className={cn('rounded px-2 py-1 font-medium transition-colors', directionFilter === 'IN' ? 'bg-good/15 text-good-text shadow-2xs' : 'text-muted-foreground hover:text-foreground')}
              >
                + In
              </button>
              <button
                type="button"
                onClick={() => setDirectionFilter('OUT')}
                className={cn('rounded px-2 py-1 font-medium transition-colors', directionFilter === 'OUT' ? 'bg-card text-foreground shadow-2xs' : 'text-muted-foreground hover:text-foreground')}
              >
                − Out
              </button>
              <button
                type="button"
                onClick={() => setDirectionFilter('transfer')}
                className={cn('rounded px-2 py-1 font-medium transition-colors', directionFilter === 'transfer' ? 'bg-card text-foreground shadow-2xs' : 'text-muted-foreground hover:text-foreground')}
              >
                ⇄ Transfer
              </button>
            </div>
          </div>
        )}
      </div>

      {hasActiveFilters && (
        <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
          <span>
            Found <strong className="font-medium text-foreground">{filtered.length}</strong> matching transactions
          </span>
          <button type="button" onClick={resetFilters} className="text-primary hover:underline font-medium">
            Reset filters
          </button>
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed px-6 py-10 text-center">
          <Mail className="mx-auto size-6 text-muted-foreground" aria-hidden />
          <p className="mt-3 font-medium">{hasActiveFilters ? 'No transactions match filters' : t('be.emptyTitle')}</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {hasActiveFilters ? 'Try adjusting your search query or direction filter.' : t('be.emptyBody', { address })}
          </p>
          {hasActiveFilters && (
            <Button variant="outline" size="sm" className="mt-4" onClick={resetFilters}>
              Clear Filters
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <ol className="overflow-hidden rounded-xl border bg-card">
            {pagedAlerts.map((a) => {
              const [label, tone] = state(a);
              const hold = holdReason(a, ctx);
              const Icon = a.transfer_with ? ArrowLeftRight : a.direction === 'IN' ? ArrowDownLeft : ArrowUpRight;
              const isEditing = editingId === a.id;
              return (
                <li key={a.id} className="border-b last:border-b-0 transition-colors hover:bg-muted/15">
                  <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-4 py-3 sm:grid-cols-[auto_minmax(0,1fr)_auto_auto]">
                    <span
                      className={cn(
                        'grid size-8 place-items-center rounded-lg shrink-0',
                        a.transfer_with ? 'bg-muted text-ink-2' : a.direction === 'IN' ? 'bg-good/10 text-good-text' : 'bg-muted text-ink-2',
                      )}
                    >
                      <Icon className="size-4" aria-hidden />
                    </span>

                    <div className="min-w-0 flex-1">
                      {isEditing ? (
                        <div className="my-1.5 flex flex-col gap-2 rounded-lg border bg-muted/40 p-2 text-xs">
                          <div className="flex items-center gap-2">
                            <span className="w-16 shrink-0 font-medium text-muted-foreground">Merchant:</span>
                            <Input
                              value={editCounterparty}
                              onChange={(e) => setEditCounterparty(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') void saveEdit(a.id);
                                else if (e.key === 'Escape') cancelEdit();
                              }}
                              className="h-7 text-xs bg-background"
                              placeholder="Counterparty / Merchant"
                              autoFocus
                            />
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="w-16 shrink-0 font-medium text-muted-foreground">Note:</span>
                            <Input
                              value={editNote}
                              onChange={(e) => setEditNote(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') void saveEdit(a.id);
                                else if (e.key === 'Escape') cancelEdit();
                              }}
                              className="h-7 text-xs bg-background"
                              placeholder="Accounting note (optional)"
                            />
                          </div>
                          <div className="flex justify-end gap-1.5 pt-1">
                            <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={cancelEdit}>
                              Cancel
                            </Button>
                            <Button size="sm" className="h-6 text-xs" disabled={savingEdit} onClick={() => saveEdit(a.id)}>
                              Save
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <p className="truncate text-sm font-medium">
                            {a.transfer_with ? t('be.transfer') : a.counterparty ?? (a.direction === 'IN' ? t('be.moneyIn') : t('be.moneyOut'))}
                          </p>
                          <button
                            type="button"
                            onClick={() => startEdit(a)}
                            className="text-muted-foreground/50 hover:text-foreground transition-colors"
                            title="Edit merchant or note"
                            aria-label="Edit merchant or note"
                          >
                            <Pencil className="size-3" />
                          </button>
                        </div>
                      )}

                      <p className="truncate text-xs text-muted-foreground">
                        {formatDate(a.occurred_on)} · {a.bank} <Tail tail={a.account_tail} />
                        {a.note && <span className="ml-2 font-normal text-foreground/80 italic">· {a.note}</span>}
                      </p>
                    </div>

                    <div className="text-right">
                      <p className={cn('figures text-sm font-semibold', a.direction === 'IN' && !a.transfer_with && 'text-good-text')}>
                        {a.direction === 'IN' ? '+' : '−'}
                        {formatMoney(a.amount, a.currency)}
                      </p>
                      {a.balance_after && <p className="figures text-[11px] text-muted-foreground">{t('be.balanceAfter', { v: formatMoney(a.balance_after, a.currency) })}</p>}
                    </div>

                    <div className="col-span-full flex flex-wrap items-center justify-end gap-1.5 sm:col-span-1 sm:w-auto">
                      <Chip tone={tone}>{label}</Chip>
                      {hold === 'currency' && ctx.currency && !counted.has(a.id) && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-6 text-[11px] gap-1 px-2 border-primary/40 text-primary hover:bg-primary/10"
                          onClick={() => startConvert(a)}
                        >
                          <RefreshCw className="size-3" />
                          {t('be.convertAlert')}
                        </Button>
                      )}
                    </div>
                  </div>

                  {a.gap && (
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-dashed border-warning/40 bg-warning/5 px-4 py-2 text-xs text-warning-text">
                      <TriangleAlert className="size-3.5 shrink-0" aria-hidden />
                      <span className="min-w-0 flex-1">{t('be.gap', { v: formatMoney(a.gap.replace('-', ''), a.currency) })}</span>
                      {counted.has(a.id) && a.balance_after && latest.get(`${a.bank_domain}|${a.account_tail}|${a.currency}`) === a.id && (
                        <Button size="sm" variant="outline" className="h-7 border-warning/50 text-xs" onClick={() => useBankBalance(a)}>
                          {t('be.useBankBalance')}
                        </Button>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ol>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="flex flex-wrap items-center justify-between gap-3 px-1 pt-1 text-xs text-muted-foreground">
              <span>
                Showing <strong className="font-medium text-foreground">{(currentPage - 1) * pageSize + 1}</strong> to{' '}
                <strong className="font-medium text-foreground">{Math.min(currentPage * pageSize, filtered.length)}</strong> of{' '}
                <strong className="font-medium text-foreground">{filtered.length}</strong> transactions
              </span>
              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={currentPage <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="h-8 gap-1 px-2.5 text-xs"
                >
                  <ChevronLeft className="size-3.5" aria-hidden />
                  Previous
                </Button>
                <span className="figures px-2 font-medium text-foreground">
                  {currentPage} / {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={currentPage >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="h-8 gap-1 px-2.5 text-xs"
                >
                  Next
                  <ChevronRight className="size-3.5" aria-hidden />
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Dialog for converting foreign currency alert to home currency */}
      <Dialog open={!!convertingAlert} onOpenChange={(open) => { if (!open) setConvertingAlert(null); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <RefreshCw className="size-4 text-primary" />
              {t('be.convertTitle')}
            </DialogTitle>
            <DialogDescription className="text-xs">
              {t('be.convertDesc')}
            </DialogDescription>
          </DialogHeader>

          {conversionLoading ? (
            <div className="flex flex-col items-center justify-center py-8 gap-2 text-xs text-muted-foreground">
              <RefreshCw className="size-5 animate-spin text-primary" />
              <span>Fetching live exchange rate...</span>
            </div>
          ) : conversionError ? (
            <div className="rounded-lg border border-critical/30 bg-critical/5 p-3 text-xs text-critical-text space-y-2">
              <p className="font-medium">Failed to retrieve exchange rate</p>
              <p>{conversionError}</p>
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => convertingAlert && startConvert(convertingAlert)}>
                Retry
              </Button>
            </div>
          ) : conversionQuote && convertingAlert && ctx.currency ? (
            <div className="space-y-3.5 py-1 text-xs">
              <div className="rounded-xl border bg-muted/20 p-3 space-y-2.5">
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>Source Transaction:</span>
                  <span className="font-medium text-foreground">
                    {convertingAlert.bank} ••{convertingAlert.account_tail}
                  </span>
                </div>
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>Original Amount:</span>
                  <span className="font-semibold text-foreground figures text-sm">
                    {formatMoney(convertingAlert.amount, convertingAlert.currency)}
                  </span>
                </div>
                <div className="flex items-center justify-between border-t border-dashed pt-2 text-muted-foreground">
                  <span>{t('be.convertExchangeRate')}:</span>
                  <span className="font-mono text-[11px] text-foreground">
                    1 {conversionQuote.from_currency} = {conversionQuote.spot_exchange_rate} {conversionQuote.to_currency}
                  </span>
                </div>
                <div className="flex items-center justify-between border-t pt-2">
                  <span className="font-medium text-foreground">{t('be.convertConvertedAmount')} ({ctx.currency}):</span>
                  <span className={cn('figures text-base font-bold', convertingAlert.direction === 'IN' ? 'text-good-text' : 'text-foreground')}>
                    {convertingAlert.direction === 'IN' ? '+' : '−'}
                    {formatMoney(conversionQuote.net_converted_amount, ctx.currency)}
                  </span>
                </div>
              </div>

              <p className="text-[11px] text-muted-foreground leading-relaxed">
                Source: <span className="font-medium">{conversionQuote.exchange_rate_source}</span>. Once confirmed, this amount will be applied to your live cash balance in {ctx.currency}.
              </p>
            </div>
          ) : null}

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="ghost" size="sm" onClick={() => setConvertingAlert(null)} disabled={convertingApplying}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={applyConversion}
              disabled={conversionLoading || !!conversionError || convertingApplying || !conversionQuote}
              className="gap-1.5"
            >
              {convertingApplying ? <RefreshCw className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
              {convertingApplying ? t('be.convertApplying') : t('be.convertConfirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

/* ------------------------------------------------------------------ trusted senders */

interface BuiltInBank {
  domain: string;
  name: string;
  currency: string;
}

const POPULAR_CURRENCIES = [
  'USD',
  'EUR',
  'GBP',
  'CAD',
  'AUD',
  'JPY',
  'CHF',
  'CNY',
  'SGD',
  'HKD',
  'INR',
  'BDT',
  'AED',
  'SAR',
  'BRL',
  'MXN',
];

function cleanBankDomain(input: string): string {
  let s = (input || '').trim().toLowerCase();
  s = s.replace(/^(mailto:|https?:\/\/)/i, '');
  if (s.includes('@')) {
    s = s.split('@')[1];
  }
  s = s.split('/')[0].split('?')[0].split('#')[0].split(':')[0].trim();
  s = s.replace(/^\.+|\.+$/g, '');
  return s;
}

function inferBankName(cleanDomain: string): string {
  if (!cleanDomain) return '';
  const labels = cleanDomain.toLowerCase().split('.');
  if (labels.length === 0) return '';
  const filtered = labels.filter(
    (p) => !['alerts', 'notify', 'notifications', 'email', 'mail', 'ebank', 'online', 'service', 'secure', 'm', 'www', 'auth'].includes(p)
  );
  const workLabels = filtered.length > 0 ? filtered : labels;

  const core =
    workLabels.length >= 3 && ['co', 'com', 'net', 'org', 'ac', 'gov'].includes(workLabels[workLabels.length - 2])
      ? workLabels[workLabels.length - 3]
      : workLabels.length >= 2
      ? workLabels[workLabels.length - 2]
      : workLabels[0];

  const KNOWN: Record<string, string> = {
    chase: 'Chase',
    bankofamerica: 'Bank of America',
    wellsfargo: 'Wells Fargo',
    citi: 'Citi',
    citibank: 'Citibank',
    capitalone: 'Capital One',
    barclays: 'Barclays',
    hsbc: 'HSBC',
    icbc: 'ICBC',
    ccb: 'China Construction Bank',
    boc: 'Bank of China',
    dbs: 'DBS',
    ocbc: 'OCBC',
    uob: 'UOB',
    bmo: 'BMO',
    cibc: 'CIBC',
    rbc: 'RBC',
    royalbank: 'RBC Royal Bank',
    scotiabank: 'Scotiabank',
    anz: 'ANZ',
    nab: 'NAB',
    westpac: 'Westpac',
    commbank: 'CommBank',
    tsb: 'TSB',
    rbs: 'Royal Bank of Scotland',
    ubs: 'UBS',
    bbva: 'BBVA',
    santander: 'Santander',
    svb: 'Silicon Valley Bank',
    pnc: 'PNC Bank',
    td: 'TD Bank',
    tdbank: 'TD Bank',
    stripe: 'Stripe',
    paypal: 'PayPal',
    wise: 'Wise',
    revolut: 'Revolut',
    monzo: 'Monzo',
    mercury: 'Mercury',
    brex: 'Brex',
    ramp: 'Ramp',
  };

  if (KNOWN[core]) return KNOWN[core];

  return core
    .replace(/[-_]+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function inferCurrencyFromDomain(cleanDomain: string, homeCurrency: string = 'USD'): string {
  const d = cleanDomain.toLowerCase();
  if (d.endsWith('.uk') || d.endsWith('.co.uk')) return 'GBP';
  if (
    d.endsWith('.eu') ||
    d.endsWith('.de') ||
    d.endsWith('.fr') ||
    d.endsWith('.it') ||
    d.endsWith('.es') ||
    d.endsWith('.nl') ||
    d.endsWith('.ie') ||
    d.endsWith('.be') ||
    d.endsWith('.at') ||
    d.endsWith('.fi') ||
    d.endsWith('.pt') ||
    d.endsWith('.gr')
  ) {
    return 'EUR';
  }
  if (d.endsWith('.ca')) return 'CAD';
  if (d.endsWith('.au') || d.endsWith('.com.au')) return 'AUD';
  if (d.endsWith('.nz') || d.endsWith('.co.nz')) return 'NZD';
  if (d.endsWith('.jp') || d.endsWith('.co.jp')) return 'JPY';
  if (d.endsWith('.ch')) return 'CHF';
  if (d.endsWith('.sg') || d.endsWith('.com.sg')) return 'SGD';
  if (d.endsWith('.hk') || d.endsWith('.com.hk')) return 'HKD';
  if (d.endsWith('.cn') || d.endsWith('.com.cn')) return 'CNY';
  if (d.endsWith('.in') || d.endsWith('.co.in')) return 'INR';
  if (d.endsWith('.bd') || d.endsWith('.com.bd')) return 'BDT';
  if (d.endsWith('.ae')) return 'AED';
  if (d.endsWith('.sa')) return 'SAR';
  if (d.endsWith('.br') || d.endsWith('.com.br')) return 'BRL';
  if (d.endsWith('.mx') || d.endsWith('.com.mx')) return 'MXN';
  return homeCurrency || 'USD';
}

function DirectoryDialog({
  builtIn,
  open,
  onOpenChange,
  onAddCustom,
}: {
  builtIn: BuiltInBank[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAddCustom: () => void;
}) {
  const { t } = useT();
  const [search, setSearch] = useState('');
  const [region, setRegion] = useState<'all' | 'americas' | 'europe' | 'apac' | 'fintech'>('all');

  const filtered = useMemo(() => {
    let list = builtIn;
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (b) =>
          b.name.toLowerCase().includes(q) ||
          b.domain.toLowerCase().includes(q) ||
          b.currency.toLowerCase().includes(q)
      );
    }
    if (region === 'americas') {
      list = list.filter((b) => ['USD', 'CAD', 'BRL', 'MXN'].includes(b.currency));
    } else if (region === 'europe') {
      list = list.filter((b) => ['GBP', 'EUR', 'CHF'].includes(b.currency));
    } else if (region === 'apac') {
      list = list.filter((b) => ['CNY', 'HKD', 'SGD', 'JPY', 'AUD', 'INR'].includes(b.currency));
    } else if (region === 'fintech') {
      const fintechDomains = [
        'stripe.com',
        'paypal.com',
        'wise.com',
        'revolut.com',
        'mercury.com',
        'brex.com',
        'ramp.com',
        'relayfi.com',
        'cash.app',
        'square.com',
        'squareup.com',
        'airwallex.com',
        'payoneer.com',
        'venmo.com',
        'shopify.com',
      ];
      list = list.filter((b) => fintechDomains.includes(b.domain));
    }
    return list;
  }, [builtIn, search, region]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <div className="flex items-center gap-2.5">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Building2 className="size-5" />
            </div>
            <div>
              <DialogTitle className="text-base font-semibold">{t('be.directoryTitle')}</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                {t('be.directoryDesc')}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-3 pt-1">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('be.searchBanks')}
              className="h-9 pl-9 pr-8 text-xs"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
                aria-label="Clear search"
              >
                <X className="size-3.5" />
              </button>
            )}
          </div>

          <div className="flex flex-wrap gap-1.5 text-xs">
            <button
              type="button"
              onClick={() => setRegion('all')}
              className={cn(
                'rounded-full px-2.5 py-1 font-medium transition-colors',
                region === 'all'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground'
              )}
            >
              {t('be.allRegions')} ({builtIn.length})
            </button>
            <button
              type="button"
              onClick={() => setRegion('americas')}
              className={cn(
                'rounded-full px-2.5 py-1 font-medium transition-colors',
                region === 'americas'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground'
              )}
            >
              Americas
            </button>
            <button
              type="button"
              onClick={() => setRegion('europe')}
              className={cn(
                'rounded-full px-2.5 py-1 font-medium transition-colors',
                region === 'europe'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground'
              )}
            >
              Europe & UK
            </button>
            <button
              type="button"
              onClick={() => setRegion('apac')}
              className={cn(
                'rounded-full px-2.5 py-1 font-medium transition-colors',
                region === 'apac'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground'
              )}
            >
              Asia-Pacific
            </button>
            <button
              type="button"
              onClick={() => setRegion('fintech')}
              className={cn(
                'rounded-full px-2.5 py-1 font-medium transition-colors',
                region === 'fintech'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground'
              )}
            >
              FinTech & Neo
            </button>
          </div>

          <ScrollArea className="h-[340px] rounded-lg border bg-muted/15 p-2">
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center text-xs text-muted-foreground">
                <Search className="size-8 opacity-30 mb-2" />
                <p className="font-medium text-foreground">No banks match &ldquo;{search}&rdquo;</p>
                <p className="mt-1 max-w-xs">You can add this institution as a custom sender domain.</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    onOpenChange(false);
                    onAddCustom();
                  }}
                  className="mt-3 h-8 text-xs gap-1.5"
                >
                  <Plus className="size-3.5" />
                  {t('be.addCustomBank')}
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {filtered.map((b) => {
                  const initials = b.name
                    .split(' ')
                    .filter(Boolean)
                    .slice(0, 2)
                    .map((w) => w[0]?.toUpperCase() ?? '')
                    .join('');
                  return (
                    <div
                      key={b.domain}
                      className="flex items-center justify-between gap-2.5 rounded-lg border bg-card p-2.5 text-xs shadow-xs hover:border-primary/30 transition-colors"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary/10 font-mono font-semibold text-[11px] text-primary">
                          {initials || 'BK'}
                        </div>
                        <div className="min-w-0">
                          <p className="font-medium text-foreground truncate">{b.name}</p>
                          <p className="font-mono text-[11px] text-muted-foreground truncate">{b.domain}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <Badge variant="outline" className="font-mono text-[10px] px-1.5 py-0 h-5">
                          {b.currency}
                        </Badge>
                        <span className="flex items-center text-good" title="Native Support">
                          <ShieldCheck className="size-3.5" />
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </ScrollArea>
        </div>

        <DialogFooter className="flex items-center justify-between sm:justify-between pt-2">
          <p className="text-xs text-muted-foreground">
            {filtered.length} of {builtIn.length} institutions
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                onOpenChange(false);
                onAddCustom();
              }}
              className="text-xs gap-1.5"
            >
              <Plus className="size-3.5" />
              {t('be.addCustomBank')}
            </Button>
            <DialogClose asChild>
              <Button size="sm" variant="ghost" className="text-xs">
                {t('common.close')}
              </Button>
            </DialogClose>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AddBankDialog({
  builtIn,
  ownDomains,
  open,
  onOpenChange,
  onSuccess,
  onOpenDirectory,
}: {
  builtIn: BuiltInBank[];
  ownDomains: [string, { name: string; currency: string }][];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
  onOpenDirectory?: () => void;
}) {
  const { t } = useT();
  const { homeCurrency } = useWorkspace();
  const [rawInput, setRawInput] = useState('');
  const [name, setName] = useState('');
  const [currency, setCurrency] = useState(homeCurrency || 'USD');
  const [nameEdited, setNameEdited] = useState(false);
  const [currencyEdited, setCurrencyEdited] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const cleanDomain = useMemo(() => cleanBankDomain(rawInput), [rawInput]);
  const isValidDomain = useMemo(
    () => /^[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63}){1,6}$/i.test(cleanDomain),
    [cleanDomain]
  );

  useEffect(() => {
    if (!nameEdited) {
      const inferred = inferBankName(cleanDomain);
      setName(inferred);
    }
    if (!currencyEdited) {
      const inferredCurr = inferCurrencyFromDomain(cleanDomain, homeCurrency);
      setCurrency(inferredCurr);
    }
  }, [cleanDomain, nameEdited, currencyEdited, homeCurrency]);

  const matchingNative = useMemo(
    () =>
      cleanDomain
        ? builtIn.find((b) => cleanDomain === b.domain || cleanDomain.endsWith('.' + b.domain))
        : null,
    [cleanDomain, builtIn]
  );

  const matchingCustom = useMemo(
    () => (cleanDomain ? ownDomains.find(([d]) => d === cleanDomain) : null),
    [cleanDomain, ownDomains]
  );

  const canSubmit =
    isValidDomain &&
    name.trim().length > 0 &&
    !matchingNative &&
    !matchingCustom &&
    !submitting;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    const ok = await mailDo(() =>
      mailApi.addBank({ domain: cleanDomain, name: name.trim(), currency })
    );
    setSubmitting(false);
    if (ok) {
      setRawInput('');
      setName('');
      setNameEdited(false);
      setCurrencyEdited(false);
      onOpenChange(false);
      onSuccess?.();
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2.5">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Globe className="size-5" />
            </div>
            <div>
              <DialogTitle className="text-base font-semibold">{t('be.addBankTitle')}</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                {t('be.addBankDesc')}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-1">
          <div className="space-y-1.5">
            <Label htmlFor="add-bank-domain" className="text-xs font-medium">
              {t('be.domainLabel')}
            </Label>
            <Input
              id="add-bank-domain"
              value={rawInput}
              onChange={(e) => setRawInput(e.target.value)}
              placeholder={t('be.domainPlaceholder')}
              className="h-9 font-mono text-xs"
              autoFocus
              required
            />
            {cleanDomain && cleanDomain !== rawInput.trim().toLowerCase() && (
              <p className="text-[11px] text-muted-foreground">
                {t('be.cleanedDomain', { domain: cleanDomain })}
              </p>
            )}

            {matchingNative && (
              <div className="flex items-start gap-2.5 rounded-lg border border-good/30 bg-good/10 p-3 text-xs">
                <CheckCircle2 className="size-4 shrink-0 text-good mt-0.5" />
                <div className="space-y-1">
                  <p className="font-medium text-good-text">
                    {matchingNative.name} ({matchingNative.currency}) is natively supported!
                  </p>
                  <p className="text-muted-foreground leading-relaxed text-[11px]">
                    Alerts from <code className="font-mono text-foreground">{cleanDomain}</code> are already parsed automatically without any custom configuration.
                  </p>
                  {onOpenDirectory && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        onOpenChange(false);
                        onOpenDirectory();
                      }}
                      className="mt-1 h-7 text-xs"
                    >
                      {t('be.viewDirectory')}
                    </Button>
                  )}
                </div>
              </div>
            )}

            {matchingCustom && (
              <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 p-2.5 text-xs text-warning-text">
                <TriangleAlert className="size-4 shrink-0 text-warning mt-0.5" />
                <span>{t('be.alreadyCustom', { domain: cleanDomain })}</span>
              </div>
            )}

            {!isValidDomain && rawInput.trim() && !matchingNative && !matchingCustom && (
              <p className="text-[11px] text-critical-text">{t('be.invalidDomain')}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="add-bank-name" className="text-xs font-medium">
              {t('be.bankName')}
            </Label>
            <Input
              id="add-bank-name"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setNameEdited(true);
              }}
              placeholder="e.g. Mercury Bank"
              className="h-9 text-xs"
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium">{t('be.currency')}</Label>
            <Select
              value={currency}
              onValueChange={(val) => {
                setCurrency(val);
                setCurrencyEdited(true);
              }}
            >
              <SelectTrigger className="h-9 text-xs font-mono">
                <SelectValue placeholder="Select currency" />
              </SelectTrigger>
              <SelectContent className="max-h-60">
                <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Popular Currencies
                </div>
                {POPULAR_CURRENCIES.map((code) => {
                  const meta = WORLD_CURRENCIES.find((c) => c.code === code);
                  return (
                    <SelectItem key={code} value={code} className="text-xs">
                      <span className="flex items-center gap-2">
                        <span className="font-mono font-semibold">{code}</span>
                        <span className="text-muted-foreground">({meta?.symbol ?? code})</span>
                        {meta && <span className="text-muted-foreground truncate">— {meta.name}</span>}
                      </span>
                    </SelectItem>
                  );
                })}
                <div className="my-1 border-t" />
                <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  All World Currencies
                </div>
                {WORLD_CURRENCIES.filter((c) => !POPULAR_CURRENCIES.includes(c.code)).map((c) => (
                  <SelectItem key={c.code} value={c.code} className="text-xs">
                    <span className="flex items-center gap-2">
                      <span className="font-mono font-semibold">{c.code}</span>
                      <span className="text-muted-foreground">({c.symbol})</span>
                      <span className="text-muted-foreground truncate">— {c.name}</span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="rounded-lg border bg-muted/20 p-3 space-y-2">
            <div className="flex items-center justify-between text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              <span>{t('be.previewTitle')}</span>
              <span className="text-primary font-normal lowercase tracking-normal">matches alerts</span>
            </div>
            <div className="flex items-center justify-between gap-3 rounded-md border bg-card p-2.5 shadow-2xs">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary font-mono font-semibold text-xs">
                  {name ? name.slice(0, 2).toUpperCase() : 'BK'}
                </div>
                <div className="min-w-0">
                  <p className="font-medium text-xs truncate text-foreground">{name || 'Your Bank'}</p>
                  <p className="font-mono text-[11px] text-muted-foreground truncate">
                    alerts@{cleanDomain || 'bank.com'}
                  </p>
                </div>
              </div>
              <div className="text-right shrink-0">
                <p className="figures font-mono font-semibold text-xs text-good-text">
                  +{formatMoney(1250, currency)}
                </p>
                <p className="text-[10px] text-muted-foreground">Account ••4821</p>
              </div>
            </div>
          </div>

          <DialogFooter className="pt-2">
            <DialogClose asChild>
              <Button type="button" variant="ghost" size="sm" className="text-xs">
                {t('common.cancel')}
              </Button>
            </DialogClose>
            <Button
              type="submit"
              size="sm"
              disabled={!canSubmit}
              className="text-xs"
            >
              {submitting && <RefreshCw className="mr-1.5 size-3.5 animate-spin" />}
              {t('be.add')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Senders({ state }: { state: MailState }) {
  const { t } = useT();
  const [builtIn, setBuiltIn] = useState<BuiltInBank[]>([]);
  const [directoryOpen, setDirectoryOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);

  useEffect(() => {
    mailApi.banks().then(
      (r) => setBuiltIn(r.banks),
      () => {}
    );
  }, []);

  const own = Object.entries(state.banks);

  return (
    <section className="space-y-4 rounded-xl border bg-card p-5">
      <div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex size-7 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Building2 className="size-4" />
            </div>
            <h2 className="font-display text-base font-semibold tracking-tight">{t('be.senders')}</h2>
          </div>
          <Badge variant="secondary" className="font-mono text-[10px]">
            {builtIn.length} built-in
          </Badge>
        </div>
        <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{t('be.sendersBody')}</p>
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setDirectoryOpen(true)}
          className="flex-1 h-8 text-xs gap-1.5"
        >
          <Search className="size-3.5" aria-hidden />
          {t('be.browseDirectory', { n: builtIn.length })}
        </Button>
        <Button
          variant="default"
          size="sm"
          onClick={() => setAddOpen(true)}
          className="h-8 text-xs gap-1"
        >
          <Plus className="size-3.5" aria-hidden />
          {t('be.add')}
        </Button>
      </div>

      {own.length > 0 ? (
        <div className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {t('be.customSenders')} ({own.length})
          </p>
          <ul className="divide-y rounded-lg border bg-muted/10">
            {own.map(([d, b]) => {
              const initials = b.name
                .split(' ')
                .filter(Boolean)
                .slice(0, 2)
                .map((w) => w[0]?.toUpperCase() ?? '')
                .join('');
              return (
                <li key={d} className="flex items-center justify-between gap-2 p-2.5 text-xs">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-accent font-mono font-semibold text-[11px] text-foreground">
                      {initials || 'BK'}
                    </div>
                    <div className="min-w-0">
                      <p className="font-medium text-foreground truncate">{b.name}</p>
                      <p className="font-mono text-[11px] text-muted-foreground truncate">{d}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Badge variant="outline" className="font-mono text-[10px] px-1.5 py-0 h-5">
                      {b.currency}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-6 text-muted-foreground hover:text-critical"
                      aria-label={t('be.removeSender', { name: b.name })}
                      onClick={() => mailDo(() => mailApi.removeBank(d))}
                    >
                      <Trash2 className="size-3.5" aria-hidden />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed bg-muted/15 p-4 text-center">
          <ShieldCheck className="mx-auto size-7 text-primary/70 mb-1.5" />
          <p className="font-medium text-xs text-foreground">{t('be.noCustomSenders')}</p>
          <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">
            {t('be.noCustomSendersDesc')}
          </p>
        </div>
      )}

      <DirectoryDialog
        builtIn={builtIn}
        open={directoryOpen}
        onOpenChange={setDirectoryOpen}
        onAddCustom={() => setAddOpen(true)}
      />

      <AddBankDialog
        builtIn={builtIn}
        ownDomains={own}
        open={addOpen}
        onOpenChange={setAddOpen}
        onOpenDirectory={() => setDirectoryOpen(true)}
      />
    </section>
  );
}

/* ------------------------------------------------------------------ page */

function Stat({ label, value, tone }: { label: string; value: React.ReactNode; tone?: 'warning' }) {
  return (
    <div className="px-5 py-3.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn('figures font-display text-2xl font-semibold', tone === 'warning' && 'text-warning-text')}>{value}</dd>
    </div>
  );
}

export default function BankEmailsPage() {
  const { t } = useT();
  const mail = useMail();
  const { live, source, accountNames } = useWorkspace();
  const state = mail.state;

  useEffect(() => {
    if (!state && !mail.syncing) {
      void checkMail();
    }
  }, [state, mail.syncing]);

  if (mail.loading && !state) {
    return (
      <div>
        <PageHeader title={t('nav.bankEmails')} description={t('be.desc')} />
        <LoadingBlock rows={4} />
      </div>
    );
  }
  if (!state) {
    return (
      <div>
        <PageHeader title={t('nav.bankEmails')} description={t('be.desc')} />
        <ErrorState message="be.err.server" retry={checkMail} />
      </div>
    );
  }
  if (!state.connection) {
    return (
      <div>
        <PageHeader title={t('nav.bankEmails')} description={t('be.desc')} />
        <Connect />
      </div>
    );
  }

  const analysis = source === 'live' ? live.analysis : undefined;
  const targets = latestBalances(analysis).map((b) => ({ id: b.id, name: accountNames[b.id] ?? b.id }));
  const review = state.alerts.filter((a) => a.status === 'review');
  const pending = state.accounts.filter((a) => a.status === 'pending');
  const counted = new Set((live.entries ?? []).map((e) => e.alertId).filter(Boolean));
  const accounts = [...state.accounts].sort((a, b) => Number(b.status === 'pending') - Number(a.status === 'pending'));
  const latestActiveAlert = state.alerts.find((a) => a.status !== 'dismissed');

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <PageHeader title={t('nav.bankEmails')} description={t('be.desc')} />
        <Button variant="outline" size="sm" asChild className="gap-2 self-start sm:self-center shrink-0">
          <Link href="/">
            <LayoutDashboard className="size-4" />
            Live Cash Overview
          </Link>
        </Button>
      </div>
      <StatusStrip state={state} />
      {mail.error && state && (
        <div role="alert" className="mt-3 flex items-center justify-between rounded-lg border border-critical/30 bg-critical/10 px-4 py-2.5 text-sm text-critical-text">
          <div className="flex items-center gap-2">
            <TriangleAlert className="size-4 shrink-0 text-critical" aria-hidden />
            <span>
              {mail.error.code === 'UNREACHABLE' || mail.error.code === 'TIMEOUT'
                ? t('be.err.server')
                : t(ERROR_KEY[mail.error.code] ?? 'be.err.generic')}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="h-7 border-critical/30 text-xs hover:bg-critical/20" onClick={checkMail} disabled={mail.syncing}>
              <RefreshCw className={cn('mr-1 size-3', mail.syncing && 'animate-spin')} aria-hidden />
              {t('common.retry')}
            </Button>
            <button
              type="button"
              onClick={clearMailError}
              className="rounded p-1 text-muted-foreground hover:bg-critical/20 hover:text-foreground"
              aria-label="Dismiss error"
            >
              <X className="size-3.5" aria-hidden />
            </button>
          </div>
        </div>
      )}

      <dl className="grid grid-cols-2 divide-y rounded-xl border bg-card sm:grid-cols-4 sm:divide-x sm:divide-y-0">
        <Stat label={t('be.stat.accounts')} value={state.accounts.filter((a) => a.status === 'use').length} />
        <Stat label={t('be.stat.counted')} value={state.alerts.filter((a) => counted.has(a.id)).length} />
        <Stat label={t('be.stat.waiting')} value={pending.length + review.length} tone={pending.length + review.length ? 'warning' : undefined} />
        <Stat label={t('be.stat.last')} value={latestActiveAlert ? formatDate(latestActiveAlert.occurred_on) : '—'} />
      </dl>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-8">
          {accounts.length > 0 && (
            <section>
              <SectionTitle aside={t('be.accountsAside')}>{t('be.accounts')}</SectionTitle>
              <ul className="grid gap-3 md:grid-cols-2">
                {accounts.map((acc) => (
                  <AccountCard key={acc.key} acc={acc} targets={targets} />
                ))}
              </ul>
            </section>
          )}
          <ReviewList alerts={review} />
          <Feed alerts={state.alerts} address={state.connection.address} accounts={state.accounts} />
        </div>
        <div className="space-y-6 lg:self-start">
          <Senders state={state} />
          <section className="space-y-4 rounded-xl border bg-card p-5">
            <h2 className="font-display text-base font-semibold tracking-tight">{t('be.privacyTitle')}</h2>
            <PathDiagram />
            <Promises />
          </section>
        </div>
      </div>
    </div>
  );
}
