'use client';

import { useState } from 'react';
import { Landmark, RotateCw, ShieldCheck, Key, ExternalLink, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { api, type CashAnalysis } from '@/lib/api';
import { useWorkspace } from '@/lib/workspace';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';

declare global {
  interface Window {
    Plaid?: {
      create: (config: {
        token: string;
        onSuccess: (public_token: string, metadata: any) => void;
        onExit?: (err: any, metadata: any) => void;
      }) => { open: () => void; exit: () => void };
    };
  }
}

export function PlaidButton({
  variant = 'outline',
  size = 'default',
  className,
  onConnected,
}: {
  variant?: 'default' | 'outline' | 'ghost';
  size?: 'default' | 'sm' | 'lg';
  className?: string;
  onConnected?: (analysis: CashAnalysis) => void;
}) {
  const { t } = useT();
  const { update, setLive, accountNames } = useWorkspace();
  const [busy, setBusy] = useState(false);
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [clientId, setClientId] = useState('');
  const [secret, setSecret] = useState('');
  const [env, setEnv] = useState<'sandbox' | 'development' | 'production'>('development');
  const [error, setError] = useState<string | null>(null);

  const openPlaidLinkWithToken = async (linkToken: string) => {
    if (!window.Plaid) {
      const script = document.createElement('script');
      script.src = 'https://cdn.plaid.com/link/v2/stable/link-initialize.js';
      script.async = true;
      document.body.appendChild(script);
      await new Promise((resolve) => {
        script.onload = resolve;
      });
    }

    const handler = window.Plaid?.create({
      token: linkToken,
      onSuccess: async (public_token, metadata) => {
        await handleExchange(
          public_token,
          metadata?.institution?.name || 'Connected Bank',
          metadata?.institution?.institution_id || 'ins_live'
        );
      },
      onExit: () => setBusy(false),
    });

    handler?.open();
  };

  const handleOpenLink = async () => {
    setBusy(true);
    setError(null);
    try {
      const status = await api.plaidStatus();
      if (!status.configured) {
        // Needs Plaid credentials
        setConfigModalOpen(true);
        setBusy(false);
        return;
      }

      const res = await api.plaidLinkToken();
      await openPlaidLinkWithToken(res.link_token);
    } catch (e: any) {
      // If server returned not configured, show config modal
      if (e?.code === 'PLAID_NOT_CONFIGURED' || e?.status === 400) {
        setConfigModalOpen(true);
      } else {
        setError(e?.message || 'Could not connect to Open Banking service.');
      }
      setBusy(false);
    }
  };

  const handleSaveAndConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!clientId.trim() || !secret.trim()) {
      setError('Please provide both Plaid Client ID and Secret.');
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await api.plaidSaveConfig({
        client_id: clientId.trim(),
        secret: secret.trim(),
        env,
      });

      const res = await api.plaidLinkToken();
      setConfigModalOpen(false);
      await openPlaidLinkWithToken(res.link_token);
    } catch (e: any) {
      setError(e?.message || 'Failed to initialize Plaid connection.');
      setBusy(false);
    }
  };

  const handleExchange = async (publicToken: string, institutionName: string, institutionId: string) => {
    setBusy(true);
    try {
      const res = await api.plaidExchangeToken({
        public_token: publicToken,
        institution_name: institutionName,
        institution_id: institutionId,
      });

      const newNames = { ...accountNames };
      for (const a of res.analysis.accounts_breakdown ?? []) {
        newNames[a.account_id] = a.file_name;
      }

      setLive({
        analysis: res.analysis,
        underwrite: undefined,
        receivables: undefined,
        intents: [],
        entries: [],
      });

      update({
        hasData: true,
        source: 'live',
        homeCurrency: res.analysis.currency || 'USD',
        accountNames: newNames,
        intentStatus: {},
        intentDecidedAt: {},
      });

      onConnected?.(res.analysis);
    } catch (e: any) {
      setError(e?.message || 'Failed to exchange bank connection token.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Button
        variant={variant}
        size={size}
        onClick={handleOpenLink}
        disabled={busy}
        className={cn('gap-2 font-medium', className)}
      >
        {busy ? <RotateCw className="size-4 animate-spin" aria-hidden /> : <Landmark className="size-4" aria-hidden />}
        <span>{busy ? t('plaid.connecting') : t('plaid.connect')}</span>
      </Button>

      {/* Real Plaid API Configuration Modal (Shown when credentials are not yet set in .env) */}
      <Dialog open={configModalOpen} onOpenChange={setConfigModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <div className="flex items-center gap-2">
              <Landmark className="size-5 text-primary" />
              <DialogTitle className="text-base font-semibold">
                Connect Real Bank Account
              </DialogTitle>
            </div>
            <DialogDescription className="text-xs text-muted-foreground">
              CashPilot connects directly to over 12,000 commercial and personal financial institutions via Plaid Open Banking.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSaveAndConnect} className="space-y-3.5 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="plaid-client-id" className="text-xs font-medium">
                Plaid Client ID
              </Label>
              <Input
                id="plaid-client-id"
                type="text"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                placeholder="e.g. 5f8b9d..."
                className="font-mono text-xs"
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="plaid-secret" className="text-xs font-medium">
                Plaid Secret
              </Label>
              <Input
                id="plaid-secret"
                type="password"
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder="Plaid secret key"
                className="font-mono text-xs"
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="plaid-env" className="text-xs font-medium">
                Environment
              </Label>
              <select
                id="plaid-env"
                value={env}
                onChange={(e) => setEnv(e.target.value as any)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="development">Development (Connect Real Live Bank Accounts)</option>
                <option value="sandbox">Sandbox (Plaid Test Credentials)</option>
                <option value="production">Production</option>
              </select>
            </div>

            <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs text-muted-foreground space-y-1.5">
              <div className="flex items-center gap-1.5 font-medium text-foreground">
                <ShieldCheck className="size-4 text-primary shrink-0" />
                <span>Tier 1 Read-Only Security</span>
              </div>
              <p className="text-[11px] leading-relaxed">
                CashPilot only observes transaction history and balances. It cannot move funds, initiate wires, or store bank login passwords.
              </p>
            </div>

            <div className="pt-1 flex items-center justify-between text-xs text-muted-foreground">
              <a
                href="https://dashboard.plaid.com/signup"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-primary underline underline-offset-2 hover:text-primary/80"
              >
                <span>Get free Plaid keys</span>
                <ExternalLink className="size-3" />
              </a>
              <Button type="submit" size="sm" disabled={busy} className="gap-2">
                {busy && <RotateCw className="size-3.5 animate-spin" />}
                <span>Connect Real Bank</span>
                <ArrowRight className="size-3.5" />
              </Button>
            </div>

            {error && (
              <p className="text-xs text-destructive font-medium" role="alert">
                {error}
              </p>
            )}
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
