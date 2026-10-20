'use client';

import { MotionConfig } from 'motion/react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { spring } from '@/lib/motion';
import { WorkspaceProvider } from '@/lib/workspace';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <WorkspaceProvider>
      <MotionConfig reducedMotion="user" transition={spring.smooth}>
        <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
      </MotionConfig>
    </WorkspaceProvider>
  );
}
