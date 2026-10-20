// CashPilot by Blueprint brand assets. Marks are redrawn as SVG from the brand sheets (geometry and
// colours measured from the source artwork); wordmarks are the original lettering, cut to transparent PNG
// in public/brand/ because the brand typeface is not available as a web font.
import { cn } from '@/lib/utils';

export const BRAND = {
  green: '#0C7A55',
  mint: '#76E5B2',
  navy: '#0B1B34',
  blueprint: '#1F56D5',
} as const;

export function CashPilotMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={cn('shrink-0', className)} aria-hidden>
      <circle cx="32" cy="32" r="32" fill={BRAND.green} />
      <circle cx="32" cy="32" r="23" fill="none" stroke="#fff" strokeOpacity=".45" strokeWidth="1.6" strokeDasharray="2.3 2.5" />
      <path d="M47.2 17 L17 29.3 L28.6 35.6 L33.8 47 Z" fill="#fff" stroke="#fff" strokeWidth="2.4" strokeLinejoin="round" />
    </svg>
  );
}

export function BlueprintMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={cn('shrink-0', className)} aria-hidden>
      <rect width="64" height="64" rx="12" fill={BRAND.blueprint} />
      <g stroke="#fff" strokeOpacity=".22" strokeWidth=".5">
        <path d="M16.5 0V64M31.8 0V64M47.2 0V64M0 16.5H64M0 31.8H64M0 47.2H64" />
      </g>
      <g fill="none" stroke="#fff" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14.2 29.4V14.5H29.8" strokeWidth="3.4" />
        <path d="M49.8 34.4V49.4H34.4" strokeWidth="3.4" />
        <path d="M40.9 22.9 22.9 40.9" strokeWidth="1.7" />
        <path d="M37.4 19.2 44.6 26.4M19.4 37.6 26.6 44.8" strokeWidth="2.3" />
      </g>
    </svg>
  );
}

/** Original wordmark artwork; the light/dark pair swaps with the theme class. Source images are 96px tall. */
export function Wordmark({ name, height = 20, className }: { name: 'cashpilot' | 'blueprint'; height?: number; className?: string }) {
  const width = Math.round(height * (name === 'cashpilot' ? 516 : 415) / 96);
  const alt = name === 'cashpilot' ? 'CashPilot' : 'Blueprint';
  return (
    <span className={cn('inline-flex', className)}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`/brand/${name}-wordmark.png`} width={width} height={height} alt={alt} className="dark:hidden" />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`/brand/${name}-wordmark-dark.png`} width={width} height={height} alt={alt} className="hidden dark:block" />
    </span>
  );
}
