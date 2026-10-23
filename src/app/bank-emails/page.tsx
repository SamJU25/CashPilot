'use client';

import { Fragment, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import {
  ArrowDownLeft,
  ArrowLeftRight,
  ArrowUpRight,
  Building2,
  Check,
  ChevronDown,
  EyeOff,
  KeyRound,
  Laptop,
  Lock,
  Mail,
  MoreHorizontal,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { PageHeader, SectionTitle } from '@/components/common/bits';
import { ErrorState, LoadingBlock } from '@/components/common/states';
import { mailApi, type MailAccount, type MailAlert, type MailSettings, type MailState } from '@/lib/api';
import { NEW_ACCOUNT, POLL_MS, checkMail, holdReason, mailDo, newAccountId, useMail } from '@/lib/bank-emails';
import { formatDate, formatMoney } from '@/lib/format';
import { useT, type Key } from '@/lib/i18n';
import { latestBalances, useCashChange } from '@/lib/use-cash-change';
import { useWorkspace } from '@/lib/workspace';
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

/** Re-renders every few seconds so "checked 2 minutes ago" stays true. */
function useNow(every = 15_000) {
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
    await new Promise((r) => setTimeout(r, 2000));
    const state = await mailApi.state().catch(() => null);
    if (state?.connection?.address.toLowerCase() === body.address.toLowerCase()) {
      await mailDo(async () => state);
      return 'connected';
    }
  }
  return 'timeout';
}

type Stage = 'email' | 'password' | 'waiting';

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

function Connect() {
  const { t } = useT();
  const reduce = useReducedMotion();
  const [stage, setStage] = useState<Stage>('email');
  const [address, setAddress] = useState('');
  const [secret, setSecret] = useState('');
  const [show, setShow] = useState(false);
  const [settings, setSettings] = useState<MailSettings | null>(null);
  const [manual, setManual] = useState(false);
  const [usePassword, setUsePassword] = useState(false);
  const [server, setServer] = useState({ host: '', username: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Key | null>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);

  const trimmed = address.trim();
  const domain = trimmed.split('@')[1] ?? '';
  const valid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(trimmed);
  const oauth = settings?.oauth && !manual && !usePassword ? settings.oauth : null;
  const blocked = !!settings?.oauth_only && !settings.oauth && !manual && !usePassword;
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
      setUsePassword(false);
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
    } catch (x) {
      setError(ERROR_KEY[(x as { code?: string }).code ?? ''] ?? 'be.err.generic');
      passwordRef.current?.select();
    } finally {
      setBusy(false);
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
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
      <div className="mx-auto w-full max-w-[440px] rounded-2xl border bg-card px-6 py-8 shadow-sm sm:px-9 sm:py-10">
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
                      setUsePassword(true);
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
                  {!settings!.oauth_only && (
                    <>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground" aria-hidden>
                        <span className="h-px flex-1 bg-border" />
                        {t('be.si.or')}
                        <span className="h-px flex-1 bg-border" />
                      </div>
                      <Button type="button" variant="ghost" className="w-full" onClick={() => setUsePassword(true)}>
                        <KeyRound aria-hidden />
                        {t('be.usePasswordInstead')}
                      </Button>
                    </>
                  )}
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
                  {settings?.oauth && (
                    <button type="button" className="mx-auto block text-[13px] text-ink-2 underline decoration-dotted underline-offset-4 hover:text-foreground" onClick={() => setUsePassword(false)}>
                      {t('be.signInWith', { provider: OAUTH_LABEL[settings.oauth] })}
                    </button>
                  )}
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
              <Button type="button" variant="ghost" onClick={() => setStage('password')}>
                {t('be.si.cancel')}
              </Button>
            </motion.div>
          )}
        </AnimatePresence>

        <p className="mt-7 flex items-center justify-center gap-1.5 text-center text-xs text-muted-foreground">
          <Lock className="size-3 shrink-0" aria-hidden />
          {t('be.si.readOnly')}
        </p>
      </div>

      <aside className="space-y-5 rounded-xl border bg-card p-5">
        <h2 className="font-display text-base font-semibold tracking-tight">{t('be.privacyTitle')}</h2>
        <PathDiagram />
        <Promises />
      </aside>
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
  const conn = state.connection!;
  const failing = !!conn.last_error;
  const checked = mail.checkedAt ?? (conn.last_sync ? Date.parse(conn.last_sync) : null);
  const nextIn = checked ? Math.max(0, Math.round((checked + POLL_MS - now) / 1000)) : null;

  return (
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
          <p className={cn('text-sm font-medium', !failing && 'truncate')}>{failing ? t(ERROR_KEY[conn.last_error!] ?? 'be.err.generic') : t('be.watching', { address: conn.address })}</p>
          <p className="text-xs text-muted-foreground">
            {checked ? t('be.checked', { when: ago(checked, lang) }) : t('be.neverChecked')}
            {!failing && nextIn !== null && <span className="figures"> · {t('be.nextIn', { s: nextIn })}</span>}
          </p>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-2">
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
        <Dialog>
          <DialogTrigger asChild>
            <Button variant="ghost" size="sm" className="text-muted-foreground">
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
                <Button variant="destructive" onClick={() => mailDo(mailApi.disconnect)}>
                  {t('be.disconnect')}
                </Button>
              </DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ accounts */

function AccountCard({ acc, targets }: { acc: MailAccount; targets: { id: string; name: string }[] }) {
  const { t } = useT();
  const [target, setTarget] = useState<string>(acc.target ?? targets[0]?.id ?? NEW_ACCOUNT);
  const [editing, setEditing] = useState(false);
  const pending = acc.status === 'pending' || editing;
  const name = acc.target === NEW_ACCOUNT ? newAccountId(acc) : targets.find((x) => x.id === acc.target)?.name ?? acc.target;
  const save = (status: MailAccount['status']) => mailDo(() => mailApi.decideAccount(acc.key, status, status === 'use' ? target : undefined)).then(() => setEditing(false));

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
            <Button size="sm" onClick={() => save('use')}>
              <Check aria-hidden />
              {t('be.useIt')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => save('ignore')}>
              {t('be.notMine')}
            </Button>
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
  if (alerts.length === 0) return null;
  return (
    <section>
      <SectionTitle aside={t('be.reviewAside')}>{t('be.review')}</SectionTitle>
      <ul className="divide-y rounded-xl border bg-card">
        {alerts.map((a) => (
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
                <Button size="sm" variant="outline" onClick={() => mailDo(() => mailApi.decideAlert(a.id, 'trust'))}>
                  {t('be.trustBank', { bank: a.bank })}
                </Button>
              )}
              {a.account_tail && (
                <Button size="sm" variant="outline" onClick={() => mailDo(() => mailApi.decideAlert(a.id, 'accept'))}>
                  {t('be.countIt')}
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={() => mailDo(() => mailApi.decideAlert(a.id, 'dismiss'))}>
                {t('be.dismiss')}
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

/* ------------------------------------------------------------------ feed */

function Feed({ alerts, address, accounts }: { alerts: MailAlert[]; address: string; accounts: MailAccount[] }) {
  const { t } = useT();
  const { live, source, hasData } = useWorkspace();
  const apply = useCashChange();
  // Newest alert per account (alerts arrive newest first).
  const latest = new Map<string, string>();
  for (const a of alerts) if (a.status !== 'dismissed' && !latest.has(a.bank_domain + a.account_tail)) latest.set(a.bank_domain + a.account_tail, a.id);
  const useBankBalance = (a: MailAlert) => {
    const acc = accounts.find((x) => x.bank_domain === a.bank_domain && x.tail === a.account_tail && x.currency === a.currency);
    if (!acc?.target) return;
    apply({
      mode: 'SET_BALANCE',
      amount: a.balance_after!,
      accountId: acc.target === NEW_ACCOUNT ? newAccountId(acc) : acc.target,
      description: t('be.openingFrom', { bank: newAccountId(acc) }),
      effectiveDate: a.occurred_on,
    }).catch(() => {});
  };
  const analysis = source === 'live' ? live.analysis : undefined;
  const ctx = {
    sample: hasData && source !== 'live',
    currency: analysis?.currency,
    statementEnd: analysis && analysis.document_format !== 'MANUAL' ? analysis.end_date ?? undefined : undefined,
  };
  const counted = new Set((live.entries ?? []).map((e) => e.alertId).filter(Boolean));
  const shown = alerts.filter((a) => a.status !== 'dismissed' && a.status !== 'review');

  const state = (a: MailAlert): [string, 'good' | 'warning' | 'muted' | 'info'] => {
    if (counted.has(a.id)) return [t('be.st.counted'), 'good'];
    if (a.status === 'waiting') return [t('be.st.waiting'), 'warning'];
    if (a.status === 'ignored') return [t('be.st.ignored'), 'muted'];
    const hold = holdReason(a, ctx);
    if (hold) return [t(`be.st.${hold}` as Key), 'muted'];
    return [t('be.st.counting'), 'info'];
  };

  return (
    <section>
      <SectionTitle aside={t('be.feedAside')}>{t('be.feed')}</SectionTitle>
      {shown.length === 0 ? (
        <div className="rounded-xl border border-dashed px-6 py-10 text-center">
          <Mail className="mx-auto size-6 text-muted-foreground" aria-hidden />
          <p className="mt-3 font-medium">{t('be.emptyTitle')}</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{t('be.emptyBody', { address })}</p>
        </div>
      ) : (
        <ol className="overflow-hidden rounded-xl border bg-card">
          {shown.map((a) => {
            const [label, tone] = state(a);
            const Icon = a.transfer_with ? ArrowLeftRight : a.direction === 'IN' ? ArrowDownLeft : ArrowUpRight;
            return (
              <li key={a.id} className="border-b last:border-b-0">
                <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-4 py-3 sm:grid-cols-[auto_minmax(0,1fr)_auto_auto]">
                  <span
                    className={cn(
                      'grid size-8 place-items-center rounded-lg',
                      a.transfer_with ? 'bg-muted text-ink-2' : a.direction === 'IN' ? 'bg-good/10 text-good-text' : 'bg-muted text-ink-2',
                    )}
                  >
                    <Icon className="size-4" aria-hidden />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{a.transfer_with ? t('be.transfer') : a.counterparty ?? (a.direction === 'IN' ? t('be.moneyIn') : t('be.moneyOut'))}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {formatDate(a.occurred_on)} · {a.bank} <Tail tail={a.account_tail} />
                    </p>
                  </div>
                  <div className="text-right">
                    <p className={cn('figures text-sm font-semibold', a.direction === 'IN' && !a.transfer_with && 'text-good-text')}>
                      {a.direction === 'IN' ? '+' : '−'}
                      {formatMoney(a.amount, a.currency)}
                    </p>
                    {a.balance_after && <p className="figures text-[11px] text-muted-foreground">{t('be.balanceAfter', { v: formatMoney(a.balance_after, a.currency) })}</p>}
                  </div>
                  <div className="col-span-full flex justify-end sm:col-span-1 sm:w-32">
                    <Chip tone={tone}>{label}</Chip>
                  </div>
                </div>
                {a.gap && (
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-dashed border-warning/40 bg-warning/5 px-4 py-2 text-xs text-warning-text">
                    <TriangleAlert className="size-3.5 shrink-0" aria-hidden />
                    <span className="min-w-0 flex-1">{t('be.gap', { v: formatMoney(a.gap.replace('-', ''), a.currency) })}</span>
                    {/* Only the account's newest alert: an older balance would undo what came after it. */}
                    {counted.has(a.id) && a.balance_after && latest.get(a.bank_domain + a.account_tail) === a.id && (
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
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ trusted senders */

function Senders({ state }: { state: MailState }) {
  const { t } = useT();
  const [builtIn, setBuiltIn] = useState<{ domain: string; name: string }[]>([]);
  const [domain, setDomain] = useState('');
  const [name, setName] = useState('');
  const [currency, setCurrency] = useState('CNY');
  useEffect(() => {
    mailApi.banks().then((r) => setBuiltIn(r.banks), () => {});
  }, []);
  const own = Object.entries(state.banks);
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await mailDo(() => mailApi.addBank({ domain: domain.trim().toLowerCase(), name: name.trim(), currency }));
    if (ok) {
      setDomain('');
      setName('');
    }
  };

  return (
    <section className="space-y-4 rounded-xl border bg-card p-5">
      <div>
        <h2 className="font-display text-base font-semibold tracking-tight">{t('be.senders')}</h2>
        <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{t('be.sendersBody')}</p>
      </div>
      <details className="group text-sm">
        <summary className="cursor-pointer list-none text-ink-2 hover:text-foreground">
          <span className="underline decoration-dotted underline-offset-4">{t('be.builtIn', { n: builtIn.length })}</span>
        </summary>
        <ul className="mt-2 grid gap-1 text-xs text-muted-foreground">
          {builtIn.map((b) => (
            <li key={b.domain} className="flex justify-between gap-2">
              <span>{b.name}</span>
              <span className="truncate font-mono">{b.domain}</span>
            </li>
          ))}
        </ul>
      </details>
      {own.length > 0 && (
        <ul className="divide-y rounded-lg border">
          {own.map(([d, b]) => (
            <li key={d} className="flex items-center gap-2 px-3 py-2 text-sm">
              <span className="min-w-0 flex-1 truncate">
                {b.name} <span className="font-mono text-xs text-muted-foreground">{d}</span>
              </span>
              {state.trusted.includes(d) && <Chip tone="muted">{t('be.trustedTag')}</Chip>}
              <Button variant="ghost" size="icon" className="size-7" aria-label={t('be.removeSender', { name: b.name })} onClick={() => mailDo(() => mailApi.removeBank(d))}>
                <X aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} className="grid gap-2 border-t pt-4">
        <Label htmlFor="be-domain" className="text-xs font-medium text-muted-foreground">
          {t('be.addSender')}
        </Label>
        <Input id="be-domain" value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="alerts.mybank.com" className="h-9 font-mono text-xs" required />
        <div className="flex gap-2">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('be.bankName')} aria-label={t('be.bankName')} className="h-9" required />
          <Input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase().slice(0, 3))} aria-label={t('be.currency')} className="figures h-9 w-20 font-mono" required />
        </div>
        <Button type="submit" size="sm" variant="outline" className="justify-self-start">
          {t('be.add')}
        </Button>
      </form>
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

  return (
    <div className="space-y-6">
      <PageHeader title={t('nav.bankEmails')} description={t('be.desc')} />
      <StatusStrip state={state} />
      {mail.error && state && (
        <p role="alert" className="text-sm text-critical-text">
          {t(ERROR_KEY[mail.error.code] ?? 'be.err.generic')}
        </p>
      )}

      <dl className="grid grid-cols-2 divide-y rounded-xl border bg-card sm:grid-cols-4 sm:divide-x sm:divide-y-0">
        <Stat label={t('be.stat.accounts')} value={state.accounts.filter((a) => a.status === 'use').length} />
        <Stat label={t('be.stat.counted')} value={state.alerts.filter((a) => counted.has(a.id)).length} />
        <Stat label={t('be.stat.waiting')} value={pending.length + review.length} tone={pending.length + review.length ? 'warning' : undefined} />
        <Stat label={t('be.stat.last')} value={state.alerts[0] ? formatDate(state.alerts[0].occurred_on) : '—'} />
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
