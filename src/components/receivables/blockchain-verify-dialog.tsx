'use client';

import { useEffect, useState } from 'react';
import { Check, Copy, Fingerprint } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { formatMoney, stringToCents } from '@/lib/format';
import { useT } from '@/lib/i18n';
import type { Debtor } from '@/lib/types';

// shortcut: hashes only invoice number, customer and amount; the registry also keys on tax IDs, which invoice exports do not carry yet.
async function invoiceFingerprint(invoice: string, buyer: string, amount: string): Promise<string> {
  const canonical = JSON.stringify({ amount_cents: stringToCents(amount), buyer: buyer.trim().toUpperCase(), invoice_num: invoice.trim().toUpperCase() });
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical));
  return `0x${Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')}`;
}

export function BlockchainVerifyDialog({ debtor, onClose }: { debtor: Debtor | null; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const [hash, setHash] = useState<string | null>(null);
  const { t } = useT();
  const invNum = debtor?.oldest_unpaid_invoice ?? null;

  useEffect(() => {
    setHash(null);
    if (!debtor || !invNum) return;
    let cancelled = false;
    invoiceFingerprint(invNum, debtor.customer_name, debtor.total_open_balance).then((h) => !cancelled && setHash(h));
    return () => {
      cancelled = true;
    };
  }, [debtor, invNum]);

  if (!debtor) return null;

  return (
    <Dialog open={!!debtor} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-xl overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Fingerprint className="size-4 text-muted-foreground" aria-hidden />
            <DialogTitle>{t('bc.dialogTitle')}</DialogTitle>
          </div>
          <DialogDescription>{t('bc.dialogDesc')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 text-sm">
          <dl className="space-y-2.5 rounded-lg border p-3">
            <div className="flex justify-between gap-4">
              <dt className="text-muted-foreground">{t('bc.invoiceLabel')}</dt>
              <dd className="font-medium">{invNum ?? '–'}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted-foreground">{t('bc.buyerLabel')}</dt>
              <dd className="font-medium">{debtor.customer_name}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted-foreground">{t('bc.amountLabel')}</dt>
              <dd className="figures font-medium">{formatMoney(debtor.total_open_balance)}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted-foreground">{t('bc.statusLabel')}</dt>
              <dd className="font-medium">{t('bc.statusUnregistered')}</dd>
            </div>
          </dl>

          {hash && (
            <div>
              <p className="pb-1 text-xs text-muted-foreground">{t('bc.sha256Label')}</p>
              <div className="flex items-center justify-between gap-2 rounded-md border bg-card p-2.5">
                <code className="break-all font-mono text-[11px] text-ink-2 select-all">{hash}</code>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 shrink-0 px-2"
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
          )}

          <p className="text-xs leading-relaxed text-muted-foreground">{t('bc.guarantee')}</p>
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
