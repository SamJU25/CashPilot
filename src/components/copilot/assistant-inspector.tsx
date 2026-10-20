'use client';

import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ListChecks, ShieldCheck } from 'lucide-react';
import { ApprovalCard, StatusPill, ViewRequestButton } from '@/components/copilot/approval';
import { FeedRow, useFeed } from '@/components/shell/activity-panel';
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
    <div className="flex h-full min-h-0 flex-col bg-background/50">
      {/* Top Switchable Tabs */}
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
      </div>

      {/* Switchable Section Panels */}
      <div className="flex-1 min-h-0 overflow-y-auto py-3 pr-1">
        <AnimatePresence mode="wait" initial={false}>
          {activeTab === 'activity' ? (
            <motion.div
              key="inspector-panel-activity"
              initial={{ opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -3 }}
              transition={fade}
            >
              <p className="mb-3 text-xs leading-relaxed text-muted-foreground">{t('act.desc')}</p>

              {feed.length === 0 ? (
                <div className="rounded-lg border border-dashed p-5 text-center">
                  <ListChecks className="mx-auto size-6 text-muted-foreground/50" aria-hidden />
                  <p className="mt-2 text-xs font-medium text-foreground">{t('act.emptyTitle')}</p>
                  <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{t('act.emptyBody')}</p>
                </div>
              ) : (
                <ol className="space-y-4">
                  {feed.map((item) => (
                    <li key={item.id}>
                      <FeedRow item={item} />
                    </li>
                  ))}
                </ol>
              )}
            </motion.div>
          ) : (
            <motion.div
              key="inspector-panel-approvals"
              initial={{ opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -3 }}
              transition={fade}
              className="space-y-6"
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
                  <div className="rounded-lg border border-dashed p-5 text-center">
                    <ShieldCheck className="mx-auto size-6 text-muted-foreground/50" aria-hidden />
                    <p className="mt-2 text-xs font-medium text-foreground">{t('ap.emptyTitle')}</p>
                    <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{t('ap.emptyBody')}</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {pending.map((intent) => (
                      <ApprovalCard key={intent.id} intent={intent} variant="compact" />
                    ))}
                  </div>
                )}
              </div>

              {/* Section 2: Decision History */}
              {history.length > 0 && (
                <div className="border-t pt-4">
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
