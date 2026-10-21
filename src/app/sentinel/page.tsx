'use client';

import { PageHeader } from '@/components/common/bits';
import { EmptyState, ErrorState, LoadingBlock } from '@/components/common/states';
import { AutonomousSentinel } from '@/components/overview/autonomous-sentinel';
import { ANALYSIS } from '@/lib/mock/demo';
import { useData } from '@/lib/use-data';
import { useT } from '@/lib/i18n';

export default function SentinelPage() {
  const state = useData(
    () => ANALYSIS,
    (live) => live.analysis,
  );
  const { t } = useT();
  const header = <PageHeader title={t('sen.title')} description={t('sen.desc')} />;

  if (state.status === 'loading') return <>{header}<LoadingBlock rows={6} /></>;
  if (state.status === 'error') return <>{header}<ErrorState message={state.message} retry={state.retry} /></>;
  if (state.status === 'empty')
    return (
      <>
        {header}
        <EmptyState title={t('sen.emptyTitle')} body={t('sen.emptyBody')} />
      </>
    );

  return (
    <>
      {header}
      <AutonomousSentinel analysis={state.data} />
    </>
  );
}
