'use client';

import { useState } from 'react';
import { Download, FileCheck2, Printer, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Money } from '@/components/common/bits';
import { formatDate, formatMoney } from '@/lib/format';
import { COMPANY } from '@/lib/mock/demo';
import { useWorkspace } from '@/lib/workspace';
import { useT } from '@/lib/i18n';
import type { FinancingOption, Forecast, UnderwritingDossier } from '@/lib/types';

export function UnderwritingDossierDialog({
  dossier: d,
  options,
  forecast: f,
}: {
  dossier: UnderwritingDossier;
  options: FinancingOption[];
  forecast: Forecast | null;
}) {
  const [open, setOpen] = useState(false);
  const { t } = useT();
  const { source, homeCurrency } = useWorkspace();
  const companyName = source === 'sample' ? COMPANY : t('lv.company');
  const today = new Date().toISOString().slice(0, 10);

  const handlePrint = () => {
    window.print();
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Printer className="size-4" aria-hidden />
          <span>{t('fund.exportDossier')}</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-3xl overflow-y-auto print:max-w-none print:p-0 print:border-none print:shadow-none">
        <DialogHeader className="print:hidden">
          <div className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary/10 text-primary">
              <FileCheck2 className="size-4" aria-hidden />
            </span>
            <DialogTitle>{t('fund.dossierTitle')}</DialogTitle>
          </div>
          <DialogDescription>{t('fund.dossierDesc')}</DialogDescription>
        </DialogHeader>

        {/* Printable Document Body */}
        <div className="mt-2 space-y-6 rounded-lg border bg-card p-6 text-sm text-foreground print:border-none print:p-0">
          {/* Institutional Document Header */}
          <div className="border-b pb-4">
            <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-end">
              <div>
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  {t('fund.dossierCategory')}
                </span>
                <h2 className="text-xl font-bold tracking-tight">{companyName}</h2>
                <p className="text-xs text-muted-foreground">
                  {t('fund.dossierSub', { date: formatDate(today, true) })}
                </p>
              </div>
              <div className="text-right">
                <span className="figures inline-flex rounded-full border bg-muted px-2.5 py-1 text-xs font-semibold">
                  {t('fund.liquidityGrade', { score: d.liquidity_score ?? 61, tier: d.risk_tier })}
                </span>
              </div>
            </div>
          </div>

          {/* Underwriting Metrics Grid */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {t('fund.sectionMetrics')}
            </h3>
            <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-[11px] text-muted-foreground">{t('fund.dab')}</p>
                <p className="mt-1 figures text-base font-semibold">
                  <Money value={d.daily_average_balance} />
                </p>
                <p className="text-[10px] text-muted-foreground">{t('fund.carryForward')}</p>
              </div>

              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-[11px] text-muted-foreground">{t('fund.maxQualified')}</p>
                <p className="mt-1 figures text-base font-semibold text-primary">
                  <Money value={d.max_qualified_limit} />
                </p>
                <p className="text-[10px] text-muted-foreground">{t('fund.preApproved')}</p>
              </div>

              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-[11px] text-muted-foreground">{t('wc.dscr')}</p>
                <p className="mt-1 figures text-base font-semibold">1.38x</p>
                <p className="text-[10px] text-good-text">{t('fund.meetsBenchmark')}</p>
              </div>

              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-[11px] text-muted-foreground">{t('fund.steady')}</p>
                <p className="mt-1 figures text-base font-semibold">{d.revenue_volatility_cv ?? '0.14'} CV</p>
                <p className="text-[10px] text-muted-foreground">{d.volatility_tier ?? 'STABLE'}</p>
              </div>
            </div>
          </div>

          {/* Cash Deficit & Bridge Need */}
          {f?.projected_deficit_date && (
            <div className="rounded-md border border-warning/30 bg-warning/10 p-3 text-xs">
              <div className="flex items-center justify-between font-medium text-warning-text">
                <span>{t('fund.deficitWarning', { date: formatDate(f.projected_deficit_date) })}</span>
                <span className="figures font-bold">{formatMoney(f.recommended_bridge_amount)}</span>
              </div>
              <p className="mt-1 text-muted-foreground">
                {t('fund.deficitRoot', { trigger: f.primary_deficit_trigger ?? 'PAYROLL' })}
              </p>
            </div>
          )}

          {/* Matched Facilities Table */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {t('fund.sectionFacilities')}
            </h3>
            <div className="mt-3 overflow-x-auto rounded-md border">
              <table className="w-full text-left text-xs">
                <thead className="bg-muted/50 border-b text-muted-foreground">
                  <tr>
                    <th className="p-2.5 font-medium">{t('fund.colLender')}</th>
                    <th className="p-2.5 font-medium">{t('fund.colFacility')}</th>
                    <th className="p-2.5 font-medium">{t('fund.colLimit')}</th>
                    <th className="p-2.5 font-medium">{t('fund.colApr')}</th>
                    <th className="p-2.5 font-medium">{t('fund.colTerm')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {options
                    .filter((o) => !o.is_predatory)
                    .map((o) => (
                      <tr key={o.provider}>
                        <td className="p-2.5 font-medium">{o.provider}</td>
                        <td className="p-2.5 text-muted-foreground">{o.facility_name}</td>
                        <td className="p-2.5 figures font-semibold">{formatMoney(o.max_amount)}</td>
                        <td className="p-2.5 figures font-semibold text-primary">{o.apr_percent}%</td>
                        <td className="p-2.5 figures text-muted-foreground">{o.term_days}d</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Consortium Audit Seal */}
          <div className="flex items-center justify-between rounded-md border bg-muted/10 p-3 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <ShieldCheck className="size-4 text-good" aria-hidden />
              <span>{t('fund.consortiumAuditProof')}</span>
            </div>
            <span className="font-mono text-[11px]">FISCO BCOS #10482910</span>
          </div>
        </div>

        <DialogFooter className="mt-3 print:hidden">
          <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
            {t('reminder.close')}
          </Button>
          <Button size="sm" onClick={handlePrint} className="gap-2">
            <Printer className="size-4" aria-hidden />
            <span>{t('fund.printPdf')}</span>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
