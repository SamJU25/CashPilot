'use client';

import Link from 'next/link';
import { useMemo } from 'react';
import { motion } from 'motion/react';
import {
  CheckCircle2,
  History,
  ShieldCheck,
} from 'lucide-react';
import { PageHeader } from '@/components/common/bits';
import { LoadingBlock, ErrorState } from '@/components/common/states';
import { AutonomousSentinel } from '@/components/overview/autonomous-sentinel';
import { ApprovalCard } from '@/components/copilot/approval';
import { useFeed, FeedRow } from '@/components/shell/activity-panel';
import { ANALYSIS, BASE } from '@/lib/mock/demo';
import { useData } from '@/lib/use-data';
import { useIntents, useWorkspace } from '@/lib/workspace';
import { useT } from '@/lib/i18n';

export default function SentinelPage() {
  const state = useData(() => ({ analysis: ANALYSIS, base: BASE }));
  const { intentStatus, source, live } = useWorkspace();
  const intents = useIntents();
  const feed = useFeed();
  const { t } = useT();

  const pending = intents.filter((i) => (intentStatus[i.id] ?? i.status) === 'STAGED_PENDING_HITL');
  const decided = intents.filter((i) => (intentStatus[i.id] ?? i.status) !== 'STAGED_PENDING_HITL');

  if (state.status === 'loading') {
    return (
      <div className="space-y-6">
        <PageHeader title={t('sentinel.title')} description="24/7 Autonomous Financial Participant & Policy Engine" />
        <LoadingBlock rows={6} />
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className="space-y-6">
        <PageHeader title={t('sentinel.title')} description="24/7 Autonomous Financial Participant & Policy Engine" />
        <ErrorState message={state.message} retry={state.retry} />
      </div>
    );
  }

  const analysis = source === 'live' && live.analysis ? live.analysis : (state.status === 'ready' ? state.data.analysis : ANALYSIS);

  return (
    <div className="space-y-10 pb-8">
      <PageHeader
        title="Treasury Sentinel"
        description="Continuous cash runway monitoring and automated credit staging under Tier 2 governance."
      />

      {/* Main Autonomous Sentinel Engine Card */}
      <AutonomousSentinel analysis={analysis} />

      {/* Secondary Section: Staged Approvals Queue & Execution Log */}
      <div className="grid gap-8 lg:grid-cols-2 pt-2">
        {/* Left Column: Pending Actions Queue (Tier 2 Governance) */}
        <section id="approvals-heading" className="space-y-4" aria-labelledby="approvals-heading-label">
          <div className="flex items-center justify-between border-b pb-2">
            <h2 id="approvals-heading-label" className="text-sm font-semibold tracking-tight text-foreground flex items-center gap-2">
              <ShieldCheck className="size-4 text-primary" aria-hidden />
              <span>Staged Approvals ({pending.length})</span>
            </h2>
            <span className="text-xs text-muted-foreground font-mono">Tier 2 Safe Staging</span>
          </div>

          {pending.length > 0 ? (
            <div className="space-y-4">
              {pending.map((intent) => (
                <ApprovalCard key={intent.id} intent={intent} variant="full" />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed p-8 text-center text-xs text-muted-foreground">
              <CheckCircle2 className="mx-auto size-6 text-good-text mb-2" aria-hidden />
              <p className="font-medium text-foreground">No pending proposals</p>
              <p className="mt-1">All autonomous staging intents have been reviewed.</p>
            </div>
          )}

          {decided.length > 0 && (
            <div className="pt-4 space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Recently Decided ({decided.length})
              </p>
              <div className="space-y-2">
                {decided.map((intent) => (
                  <ApprovalCard key={intent.id} intent={intent} variant="compact" />
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Right Column: Audit Trail */}
        <section className="space-y-4" aria-labelledby="audit-heading">
          <div className="flex items-center justify-between border-b pb-2">
            <h2 id="audit-heading" className="text-sm font-semibold tracking-tight text-foreground flex items-center gap-2">
              <History className="size-4 text-muted-foreground" aria-hidden />
              <span>Audit Trail</span>
            </h2>
            <span className="text-xs text-muted-foreground font-mono">Immutable Log</span>
          </div>

          <div className="space-y-4 rounded-xl border bg-card p-5">
            {feed.map((item) => (
              <FeedRow key={item.id} item={item} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
