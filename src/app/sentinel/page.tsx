'use client';

import { PageHeader } from '@/components/common/bits';
import { LoadingBlock, ErrorState } from '@/components/common/states';
import { AutonomousSentinel } from '@/components/overview/autonomous-sentinel';
import { ANALYSIS, BASE } from '@/lib/mock/demo';
import { useData } from '@/lib/use-data';
import { useWorkspace } from '@/lib/workspace';

export default function SentinelPage() {
  const state = useData(() => ({ analysis: ANALYSIS, base: BASE }));
  const { source, live } = useWorkspace();

  if (state.status === 'loading') {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Treasury Sentinel"
          description="Continuous liquidity monitoring and automated credit staging under Tier 2 governance."
        />
        <LoadingBlock rows={6} />
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Treasury Sentinel"
          description="Continuous liquidity monitoring and automated credit staging under Tier 2 governance."
        />
        <ErrorState message={state.message} retry={state.retry} />
      </div>
    );
  }

  const analysis = source === 'live' && live.analysis ? live.analysis : (state.status === 'ready' ? state.data.analysis : ANALYSIS);

  return (
    <div className="space-y-8 pb-8">
      <PageHeader
        title="Treasury Sentinel"
        description="Continuous cash runway monitoring and automated credit staging under Tier 2 governance."
      />

      {/* Main Autonomous Sentinel Engine Card */}
      <AutonomousSentinel analysis={analysis} />
    </div>
  );
}
