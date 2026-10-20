import type { Metadata } from 'next';
import { IBM_Plex_Mono, IBM_Plex_Sans } from 'next/font/google';
import { AppShell } from '@/components/shell/app-shell';
import { Providers } from '@/components/shell/providers';
import './globals.css';

const sans = IBM_Plex_Sans({ subsets: ['latin'], weight: ['400', '500', '600'], variable: '--font-sans', display: 'swap' });
const mono = IBM_Plex_Mono({ subsets: ['latin'], weight: ['400', '500'], variable: '--font-mono', display: 'swap' });

const THEME_SCRIPT = `try{var t=(JSON.parse(localStorage.getItem('copilot.workspace.v1')||'{}').theme)||'system';if(t==='dark'||(t==='system'&&matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.classList.add('dark')}catch(e){}`;
const CHUNK_RELOAD_SCRIPT = `window.addEventListener('error',function(e){if(e&&e.message&&/Loading chunk .* failed/i.test(e.message)){var k='chk_retry_'+location.pathname;if(!sessionStorage.getItem(k)){sessionStorage.setItem(k,'1');location.reload();}}});`;

export const metadata: Metadata = {
  title: 'CashPilot',
  description: 'CashPilot by Blueprint: know when cash runs short, why, and what to do about it.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        {/* Applies the saved theme before first paint; the provider takes over after hydration. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <script dangerouslySetInnerHTML={{ __html: CHUNK_RELOAD_SCRIPT }} />
      </head>
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
