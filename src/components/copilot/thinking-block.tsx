'use client';

import { useT } from '@/lib/i18n';

/**
 * Shown while the model writes, for every provider. The reasoning text itself is not displayed:
 * not all models expose it, and the verifiable figures already live in the calculation receipt.
 */
export function ThinkingIndicator({ label }: { label?: string }) {
  const { t } = useT();
  return (
    <p className="shimmer-text text-xs font-medium" role="status" aria-live="polite">
      {label ?? t('as.thinking')}
    </p>
  );
}
