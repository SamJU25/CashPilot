'use client';

import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Moon, Sun } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useT } from '@/lib/i18n';
import { fade } from '@/lib/motion';
import { useWorkspace } from '@/lib/workspace';
import { cn } from '@/lib/utils';

/** One-tap light/dark switch. "System" stays selectable in Settings; tapping here picks the opposite of what is showing. */
export function ThemeSwitch({ className }: { className?: string }) {
  const { theme, update } = useWorkspace();
  const { t } = useT();
  const [systemDark, setSystemDark] = useState(false);

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const sync = () => setSystemDark(media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);

  const dark = theme === 'dark' || (theme === 'system' && systemDark);
  const label = dark ? t('rail.light') : t('rail.dark');

  return (
    <Button variant="ghost" size="icon" className={cn('size-11', className)} aria-label={label} title={label} onClick={() => update({ theme: dark ? 'light' : 'dark' })}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span key={dark ? 'sun' : 'moon'} initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }} transition={fade}>
          {dark ? <Sun aria-hidden /> : <Moon aria-hidden />}
        </motion.span>
      </AnimatePresence>
    </Button>
  );
}
