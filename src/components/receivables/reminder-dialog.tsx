'use client';

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { TierBadge } from '@/components/common/bits';
import { formatMoney } from '@/lib/format';
import { COMPANY } from '@/lib/mock/demo';
import { useWorkspace } from '@/lib/workspace';
import type { Debtor } from '@/lib/types';
import { useT, type T } from '@/lib/i18n';

function reminderText(d: Debtor, t: T, company: string) {
  return t('reminder.body', {
    inv: d.oldest_unpaid_invoice ?? '',
    company,
    name: d.customer_name,
    amount: formatMoney(d.overdue_amount),
    count: t('count.invoices', { n: d.invoice_count }),
    days: d.max_days_overdue,
  });
}

/** Tier 2: a payment reminder the owner copies and sends themselves. */
export function ReminderDialog({ debtor, onClose }: { debtor: Debtor | null; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const { t } = useT();
  const { source } = useWorkspace();
  const text = debtor ? reminderText(debtor, t, source === 'sample' ? COMPANY : t('lv.company')) : '';

  return (
    <Dialog
      open={!!debtor}
      onOpenChange={(o) => {
        if (!o) {
          onClose();
          setCopied(false);
        }
      }}
    >
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-xl overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <DialogTitle>{t('reminder.title', { name: debtor?.customer_name ?? '' })}</DialogTitle>
            <TierBadge tier={2} />
          </div>
          <DialogDescription>{t('reminder.desc')}</DialogDescription>
        </DialogHeader>
        <pre className="max-h-[min(20rem,40dvh)] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/50 p-4 font-sans text-sm leading-6">{text}</pre>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('reminder.close')}
          </Button>
          <Button
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(text);
                setCopied(true);
              } catch {
                setCopied(false);
              }
            }}
          >
            {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
            {copied ? t('reminder.copied') : t('reminder.copy')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
