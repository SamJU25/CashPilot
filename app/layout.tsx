import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'SME Finance Copilot',
  description: 'Autonomous AI CFO and Financial Participant for Small & Medium Enterprises',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>{children}</body>
    </html>
  );
}
