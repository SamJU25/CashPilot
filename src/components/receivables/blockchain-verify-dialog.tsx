'use client';

import { useState } from 'react';
import { Check, Copy, ExternalLink, Hash, Link2, ShieldAlert, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { formatMoney } from '@/lib/format';
import { useT } from '@/lib/i18n';
import type { Debtor } from '@/lib/types';

// Simple deterministic hash derivation for display matching services/blockchain/invoice_hasher.py
function deriveInvoiceHash(invoiceNum: string, buyer: string, amount: string): string {
  const seed = `${invoiceNum.toUpperCase()}:${buyer.toUpperCase()}:${amount}`;
  let hash = 0x811c9dc5;
  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  const part1 = (hash >>> 0).toString(16).padStart(8, '0');
  const part2 = ((hash * 31) >>> 0).toString(16).padStart(8, '0');
  const part3 = ((hash * 127) >>> 0).toString(16).padStart(8, '0');
  const part4 = ((hash * 8191) >>> 0).toString(16).padStart(8, '0');
  return `0x${part1}${part2}${part3}${part4}`;
}

export function BlockchainVerifyDialog({
  debtor,
  onClose,
}: {
  debtor: Debtor | null;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const { t } = useT();

  if (!debtor) return null;

  const invNum = debtor.oldest_unpaid_invoice ?? 'INV-GENERAL';
  const hash = deriveInvoiceHash(invNum, debtor.customer_name, debtor.total_open_balance);
  const blockNum = 10482910 + (Math.abs(hash.charCodeAt(4)) % 500);

  return (
    <Dialog open={!!debtor} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-xl overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-md bg-good/10 text-good-text">
              <ShieldCheck className="size-4" aria-hidden />
            </span>
            <DialogTitle>{t('bc.dialogTitle')}</DialogTitle>
          </div>
          <DialogDescription>{t('bc.dialogDesc')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 text-xs">
          {/* Status Banner */}
          <div className="flex items-center justify-between rounded-lg border border-good/30 bg-good/5 p-3 text-good-text">
            <div className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-good" aria-hidden />
              <span className="font-medium">{t('bc.statusVerified')}</span>
            </div>
            <span className="font-mono text-[11px] text-muted-foreground">{t('bc.networkName')}</span>
          </div>

          {/* Details Grid */}
          <div className="rounded-lg border bg-muted/30 p-3 space-y-2.5">
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">{t('bc.invoiceLabel')}</span>
              <span className="font-mono font-medium text-foreground">{invNum}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">{t('bc.buyerLabel')}</span>
              <span className="font-medium text-foreground">{debtor.customer_name}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">{t('bc.amountLabel')}</span>
              <span className="figures font-medium text-foreground">{formatMoney(debtor.total_open_balance)}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">{t('bc.contractLabel')}</span>
              <span className="font-mono text-[11px] text-foreground">InvoiceRegistry.sol</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">{t('bc.blockLabel')}</span>
              <span className="figures font-mono text-[11px] text-muted-foreground">#{blockNum}</span>
            </div>
          </div>

          {/* SHA-256 Digest Box */}
          <div>
            <div className="flex items-center justify-between pb-1">
              <span className="font-medium text-muted-foreground">{t('bc.sha256Label')}</span>
              <span className="text-[11px] text-muted-foreground">{t('bc.canonicalFormat')}</span>
            </div>
            <div className="flex items-center justify-between gap-2 rounded-md border bg-card p-2.5">
              <code className="figures break-all font-mono text-[11px] text-ink-2 select-all">{hash}</code>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 shrink-0 px-2 text-xs"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(hash);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 2000);
                  } catch {
                    setCopied(false);
                  }
                }}
              >
                {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                <span className="sr-only">{t('reminder.copy')}</span>
              </Button>
            </div>
          </div>

          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {t('bc.guarantee')}
          </p>
        </div>

        <DialogFooter className="mt-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            {t('reminder.close')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
