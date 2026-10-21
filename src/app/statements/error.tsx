'use client';

import { useEffect } from 'react';
import { ErrorState } from '@/components/common/states';

export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => console.error(error), [error]);
  return <ErrorState message="common.crash" retry={reset} />;
}
