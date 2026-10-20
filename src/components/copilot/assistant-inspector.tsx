'use client';

import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import Link from 'next/link';
import { Activity, ArrowRight, FileText, ListChecks, Shield, ShieldCheck } from 'lucide-react';
import { ApprovalCard, StatusPill, ViewRequestButton } from '@/components/copilot/approval';
import { FeedRow, useFeed } from '@/components/shell/activity-panel';
import { Button } from '@/components/ui/button';
import { useT, type Key } from '@/lib/i18n';
import { useIntents, useWorkspace } from '@/lib/workspace';
import { centsToString, formatDateTime, formatMoney } from '@/lib/format';
import { fade, spring } from '@/lib/motion';
import { cn } from '@/lib/utils';
import type { StagedActionIntent } from '@/lib/types';

export function AssistantInspector({
  activeTab: controlledTab,
  onTabChange,
}: {
  activeTab?: 'activity' | 'approvals';
  onTabChange?: (tab: 'activity' | 'approvals') => void;
}) {
  const { t } = useT();
  const intents = useIntents();
  const { intentStatus } = useWorkspace();
  const feed = useFeed();

  const allIntents = intents.map((i) => ({ ...i, status: intentStatus[i.id] ?? i.status }));
  const pending = allIntents.filter((i) => i.status === 'STAGED_PENDING_HITL');
  const history = allIntents.filter((i) => i.status !== 'STAGED_PENDING_HITL');
  const actionName = (i: StagedActionIntent) => t(`action.${i.action_type}` as Key);

  const [internalTab, setInternalTab] = useState<'activity' | 'approvals'>('activity');

  const activeTab = controlledTab ?? internalTab;
  const setTab = onTabChange ?? setInternalTab;

  return (
    <div className="flex h-full min-h-0 flex-col bg-transparent">
      {/* Top Switchable Tabs Toolbar */}
      <div className="flex shrink-0 items-center justify-between border-b pb-3 pt-1">
        <div className="relative flex rounded-lg bg-muted/70 p-0.5" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'activity'}
            onClick={() => setTab('activity')}
            className={cn(
              'relative z-10 flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
              activeTab === 'activity'
                ? 'text-foreground font-semibold'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {activeTab === 'activity' && (
              <motion.span
                layoutId="inspector-active-tab"
                transition={spring.snappy}
                className="absolute inset-0 rounded-md bg-background shadow-xs"
              />
            )}
            <ListChecks className="relative z-10 size-3.5" aria-hidden />
            <span className="relative z-10">{t('nav.activity')}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'approvals'}
            onClick={() => setTab('approvals')}
            className={cn(
              'relative z-10 flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
              activeTab === 'approvals'
                ? 'text-foreground font-semibold'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {activeTab === 'approvals' && (
              <motion.span
                layoutId="inspector-active-tab"
                transition={spring.snappy}
                className="absolute inset-0 rounded-md bg-background shadow-xs"
              />
            )}
            <ShieldCheck className="relative z-10 size-3.5" aria-hidden />
            <span className="relative z-10">{t('nav.approvals')}</span>
            {pending.length > 0 && (
              <span className="relative z-10 flex size-4 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
                {pending.length}
              </span>
            )}
          </button>
        </div>

        <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground pr-1">
          <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" aria-hidden />
          <span>Live Monitor</span>
        </div>
      </div>

      {/* Switchable Section Panels */}
      <div className="flex-1 min-h-0 overflow-y-auto py-3 space-y-4 pr-1">
        <AnimatePresence mode="wait" initial={false}>
          {activeTab === 'activity' ? (
            <motion.div
              key="inspector-panel-activity"
              initial={{ opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -3 }}
              transition={fade}
              className="space-y-3.5"
            >
              {/* 3-Tier Security Posture Card */}
              <div className="rounded-xl border bg-card/60 p-3.5 space-y-2.5 text-xs shadow-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-foreground text-xs flex items-center gap-1.5">
                    <Shield className="size-3.5 text-primary" aria-hidden />
                    3-Tier Security Gate
                  </span>
                  <span className="text-[10px] font-medium text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                    Enforced
                  </span>
                </div>
                <div className="space-y-1.5 text-[11px] border-t border-border/40 pt-2">
                  <div className="flex items-center justify-between text-muted-foreground">
                    <span>Tier 1 (Read-Only)</span>
                    <span className="text-foreground font-mono text-[10.5px]">Autonomous</span>
                  </div>
                  <div className="flex items-center justify-between text-muted-foreground">
                    <span>Tier 2 (Staging Queue)</span>
                    <span className="text-foreground font-mono text-[10.5px]">Drafts Only</span>
                  </div>
                  <div className="flex items-center justify-between text-muted-foreground">
                    <span>Tier 3 (Execution)</span>
                    <span className="text-amber-500 font-mono text-[10.5px]">Owner-Sent</span>
                  </div>
                </div>
              </div>

              {feed.length === 0 ? (
                <div className="space-y-3">
                  <div className="rounded-xl border bg-card/40 p-3.5 space-y-3 text-xs">
                    <div className="flex items-center gap-2">
                      <div className="flex size-6 items-center justify-center rounded-md bg-primary/10 text-primary">
                        <Activity className="size-3.5" aria-hidden />
                      </div>
                      <p className="font-medium text-foreground text-xs">{t('act.emptyTitle')}</p>
                    </div>
                    <p className="text-muted-foreground leading-relaxed text-[11.5px]">
                      {t('act.desc')}
                    </p>
                    <div className="space-y-2 border-t border-border/40 pt-2.5 text-[11px]">
                      <div className="flex items-start gap-2">
                        <span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary font-mono text-[9px] font-semibold">1</span>
                        <p className="text-muted-foreground"><strong className="text-foreground font-medium">Ingestion:</strong> Line-item PDF/CSV parsing with row balance tie-out.</p>
                      </div>
                      <div className="flex items-start gap-2">
                        <span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary font-mono text-[9px] font-semibold">2</span>
                        <p className="text-muted-foreground"><strong className="text-foreground font-medium">Deterministic Math:</strong> Daily Average Balance carry-forward, runway, and DSCR.</p>
                      </div>
                      <div className="flex items-start gap-2">
                        <span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary font-mono text-[9px] font-semibold">3</span>
                        <p className="text-muted-foreground"><strong className="text-foreground font-medium">Early Warning:</strong> Overdraft pinpointing across 30/60/90-day horizons.</p>
                      </div>
                    </div>
                  </div>

                  <Button asChild size="sm" variant="outline" className="w-full text-xs font-medium justify-between h-8">
                    <Link href="/statements">
                      <span className="flex items-center gap-1.5">
                        <FileText className="size-3.5 text-muted-foreground" aria-hidden />
                        {t('as.noDataLink')}
                      </span>
                      <ArrowRight className="size-3 text-muted-foreground" aria-hidden />
                    </Link>
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground px-0.5">
                    {t('nav.activity')}
                  </p>
                  <ol className="space-y-3">
                    {feed.map((item) => (
                      <li key={item.id}>
                        <FeedRow item={item} />
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </motion.div>
          ) : (
            <motion.div
              key="inspector-panel-approvals"
              initial={{ opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -3 }}
              transition={fade}
              className="space-y-4"
            >
              {/* Section 1: Pending HITL Approvals */}
              <div>
                <div className="mb-2.5 flex items-center justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {t('ov.waiting')}
                  </h3>
                  {pending.length > 0 && (
                    <span className="figures text-xs text-muted-foreground">
                      {t('count.actions', { n: pending.length })}
                    </span>
                  )}
                </div>

                {pending.length === 0 ? (
                  <div className="rounded-xl border bg-card/40 p-4 text-center space-y-2 text-xs">
                    <ShieldCheck className="mx-auto size-6 text-emerald-500" aria-hidden />
                    <p className="font-medium text-foreground text-xs">{t('ap.emptyTitle')}</p>
                    <p className="text-muted-foreground leading-relaxed text-[11.5px]">{t('ap.emptyBody')}</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="rounded-lg border border-warning/30 bg-warning/5 p-2.5 text-[11px] text-warning-text leading-relaxed">
                      Owner confirmation required. Proposed facilities remain queued until you prepare and send the request.
                    </div>
                    {pending.map((intent) => (
                      <ApprovalCard key={intent.id} intent={intent} variant="compact" />
                    ))}
                  </div>
                )}
              </div>

              {/* Section 2: Decision History */}
              {history.length > 0 && (
                <div className="border-t border-border/40 pt-4">
                  <h4 className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {t('ap.history')}
                  </h4>
                  <ul className="space-y-2.5">
                    {history.map((intent) => (
                      <li
                        key={intent.id}
                        className="rounded-lg border bg-card/40 p-2.5 text-xs space-y-1.5"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="font-medium text-foreground">
                            {t('ap.histTitle', {
                              action: actionName(intent),
                              amount: formatMoney(centsToString(intent.amount_cents)),
                            })}
                          </p>
                          <StatusPill status={intent.status} />
                        </div>
                        <p className="text-[11px] text-muted-foreground">
                          {t('ap.histMeta', {
                            name: intent.target_identifier,
                            time: formatDateTime(intent.staged_at),
                          })}
                        </p>
                        {intent.status === 'PREPARED' && (
                          <div className="pt-1">
                            <ViewRequestButton intent={intent} />
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
