'use client';

import { useState } from 'react';
import { Landmark, CheckCircle2, RotateCw, ShieldCheck, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { api, type CashAnalysis, type PlaidAccount } from '@/lib/api';
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

const SANDBOX_INSTITUTIONS = [
  {
    id: 'ins_svb',
    name: 'Silicon Valley Bank',
    type: 'Commercial Banking',
    accounts: 'Operating Checking & Money Market',
    logoBg: 'bg-blue-600',
  },
  {
    id: 'ins_chase',
    name: 'Chase Commercial',
    type: 'Business Treasury',
    accounts: 'Payroll & Operating Checking',
    logoBg: 'bg-sky-700',
  },
  {
    id: 'ins_mercury',
    name: 'Mercury Treasury',
    type: 'Startup & Tech Banking',
    accounts: 'Checking & Treasury Reserve',
    logoBg: 'bg-indigo-600',
  },
];

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
  const [modalOpen, setModalOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleOpenLink = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.plaidLinkToken();
      if (res.sandbox_simulated) {
        // Open local sandbox selection dialog
        setModalOpen(true);
      } else {
        // Open live Plaid Link script
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
          token: res.link_token,
          onSuccess: async (public_token, metadata) => {
            await handleExchange(public_token, metadata?.institution?.name, metadata?.institution?.institution_id);
          },
          onExit: () => setBusy(false),
        });
        handler?.open();
      }
    } catch (e: any) {
      setError(e?.message || 'Could not reach Open Banking service.');
    } finally {
      setBusy(false);
    }
  };

  const handleExchange = async (publicToken: string, institutionName?: string, institutionId?: string) => {
    setBusy(true);
    try {
      const res = await api.plaidExchangeToken({
        public_token: publicToken,
        institution_name: institutionName || 'Connected Bank',
        institution_id: institutionId || 'ins_default',
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

      setModalOpen(false);
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

      {/* Sandbox Institution Picker Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <div className="flex items-center gap-2">
              <Landmark className="size-5 text-primary" />
              <DialogTitle className="text-base font-semibold">
                {t('plaid.modalTitle')}
              </DialogTitle>
            </div>
            <DialogDescription className="text-xs text-muted-foreground">
              {t('plaid.modalDesc')}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2.5 py-3">
            {SANDBOX_INSTITUTIONS.map((inst) => (
              <button
                key={inst.id}
                type="button"
                disabled={busy}
                onClick={() => handleExchange(`public-sandbox-${inst.id}`, inst.name, inst.id)}
                className="group flex w-full items-center justify-between rounded-xl border border-border/60 bg-card p-3.5 text-left transition-all hover:border-primary/50 hover:bg-accent/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg text-white font-bold text-xs', inst.logoBg)}>
                    {inst.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <p className="font-medium text-sm text-foreground truncate">{inst.name}</p>
                    <p className="text-xs text-muted-foreground truncate">{inst.accounts}</p>
                  </div>
                </div>
                <ArrowRight className="size-4 text-muted-foreground/60 transition-transform group-hover:translate-x-0.5 group-hover:text-primary shrink-0" />
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/5 p-2.5 text-xs text-muted-foreground">
            <ShieldCheck className="size-4 text-primary shrink-0" />
            <span>{t('plaid.readOnlyBadge')}</span>
          </div>

          {error && (
            <p className="mt-2 text-xs text-critical-text font-medium" role="alert">
              {error}
            </p>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
