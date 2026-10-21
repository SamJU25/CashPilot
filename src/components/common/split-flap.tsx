'use client';

import { AnimatePresence, motion } from 'motion/react';
import { spring, STAGGER_S } from '@/lib/motion';
import { cn } from '@/lib/utils';

/**
 * Departure-board figures: one tile per character, and only tiles whose character changed flip.
 * Tiles are keyed by position so a new date flips in place instead of remounting the board.
 */
export function SplitFlap({ text, className }: { text: string; className?: string }) {
  const chars = Array.from(text);
  return (
    <span className={cn('mx-[0.08em] inline-flex items-center gap-[0.06em] align-[-0.12em] font-display uppercase', className)}>
      <span className="sr-only">{text}</span>
      {chars.map((c, i) =>
        c === ' ' ? (
          <span key={i} className="w-[0.28em]" aria-hidden />
        ) : (
          <span
            key={i}
            aria-hidden
            className="relative inline-grid h-[1.22em] min-w-[0.78em] place-items-center overflow-hidden rounded-[0.1em] bg-flap px-[0.08em] leading-none text-flap-ink [perspective:320px]"
          >
            <AnimatePresence mode="popLayout" initial>
              <motion.span
                key={c}
                className="[grid-area:1/1] [backface-visibility:hidden]"
                initial={{ rotateX: -90, opacity: 0 }}
                animate={{ rotateX: 0, opacity: 1 }}
                exit={{ rotateX: 90, opacity: 0 }}
                transition={{ ...spring.snappy, delay: i * STAGGER_S }}
              >
                {c}
              </motion.span>
            </AnimatePresence>
            {/* The seam between the two flaps. */}
            <span className="pointer-events-none absolute inset-x-0 top-1/2 h-[0.04em] -translate-y-1/2 bg-background/40" />
          </span>
        ),
      )}
    </span>
  );
}
