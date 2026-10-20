'use client';

import Link from 'next/link';
import { AlertCircle, RotateCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useT, type Key } from '@/lib/i18n';

export function EmptyState({
  title,
  body,
  className,
  action = { href: '/statements', label: 'common.add' },
}: {
  title: string;
  body: string;
  className?: string;
  action?: { href: string; label: Key } | null;
}) {
  const { t } = useT();
  return (
    <div className={cn('rounded-lg border border-dashed px-6 py-12 text-center', className)}>
      <p className="text-base font-medium">{title}</p>
      <p className="mx-auto mt-1.5 max-w-md text-sm text-muted-foreground">{body}</p>
      {action && (
        <Button asChild className="mt-5">
          <Link href={action.href}>{t(action.label)}</Link>
        </Button>
      )}
    </div>
  );
}

export function ErrorState({ message, retry, className }: { message: Key; retry: () => void; className?: string }) {
  const { t } = useT();
  return (
    <div role="alert" className={cn('flex flex-col items-start gap-3 rounded-lg border border-critical/30 bg-critical/5 p-5 sm:flex-row sm:items-center', className)}>
      <AlertCircle className="size-5 shrink-0 text-critical-text" aria-hidden />
      <div className="flex-1">
        <p className="text-sm font-medium">{t('common.loadError')}</p>
        <p className="text-sm text-muted-foreground">{t(message)}</p>
      </div>
      <Button variant="outline" size="sm" onClick={retry}>
        <RotateCw aria-hidden />
        {t('common.retry')}
      </Button>
    </div>
  );
}

export function LoadingBlock({ rows = 3, className }: { rows?: number; className?: string }) {
  const { t } = useT();
  return (
    <div className={cn('space-y-3', className)} aria-busy="true" aria-label={t('common.loading')}>
      <Skeleton className="h-6 w-1/3" />
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}
