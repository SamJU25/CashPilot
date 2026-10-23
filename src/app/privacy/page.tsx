import Link from 'next/link';

export const metadata = {
  title: 'Privacy Policy — CashPilot',
  description: 'CashPilot Privacy Policy and Google API Services User Data Policy Compliance',
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-background px-6 py-16 text-foreground">
      <div className="mx-auto max-w-3xl space-y-8">
        <header className="border-b pb-6">
          <Link href="/" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground">
            ← Back to CashPilot
          </Link>
          <h1 className="mt-4 font-display text-3xl font-bold tracking-tight">Privacy Policy</h1>
          <p className="mt-2 text-sm text-muted-foreground">Effective Date: October 24, 2026</p>
        </header>

        <section className="space-y-4">
          <h2 className="text-xl font-semibold">1. Overview</h2>
          <p className="leading-relaxed text-muted-foreground">
            CashPilot (&quot;we&quot;, &quot;our&quot;, or &quot;the Service&quot;) is an autonomous financial workspace designed to assist small and medium enterprises (SMEs) with cash runway analysis, working capital diagnostics, and transaction reconciliation. We prioritize user privacy, data minimization, and local-first data processing.
          </p>
        </section>

        <section className="space-y-4 rounded-xl border border-primary/20 bg-primary/5 p-6">
          <h2 className="text-xl font-semibold text-primary">2. Google API Services User Data Policy & Limited Use Disclosure</h2>
          <p className="leading-relaxed text-sm">
            CashPilot&apos;s use and transfer to any other app of information received from Google APIs will adhere to the{' '}
            <a
              href="https://developers.google.com/terms/api-services-user-data-policy"
              target="_blank"
              rel="noreferrer"
              className="font-medium underline underline-offset-4"
            >
              Google API Services User Data Policy
            </a>
            , including the Limited Use requirements.
          </p>
          <ul className="list-disc space-y-2 pl-5 text-sm text-muted-foreground">
            <li>
              <strong>Narrow Purpose:</strong> CashPilot requests access to email data solely to identify and parse transactional bank notifications and debit/credit alerts.
            </li>
            <li>
              <strong>No General Inbox Storage:</strong> We do not download, store, read, or catalog personal correspondence, promotional emails, or general mailbox contents.
            </li>
            <li>
              <strong>No AI Model Training:</strong> Google Workspace APIs and user email data are never used to develop, train, fine-tune, or improve generalized or non-personalized AI/ML models.
            </li>
            <li>
              <strong>No Human Access:</strong> No human employees or contractors ever read your email messages unless required by law or explicitly authorized by you for technical troubleshooting.
            </li>
          </ul>
        </section>

        <section className="space-y-4">
          <h2 className="text-xl font-semibold">3. Information We Collect</h2>
          <p className="leading-relaxed text-muted-foreground">
            When you connect an alerts mailbox via OAuth2 or upload bank statements:
          </p>
          <ul className="list-disc space-y-2 pl-5 text-muted-foreground">
            <li><strong>Bank Transaction Data:</strong> Transaction date, amount, currency code, sender institution, and account tail digits extracted from bank alert emails or uploaded statements.</li>
            <li><strong>Authentication Tokens:</strong> OAuth refresh tokens are stored encrypted on the user&apos;s device using native operating system vaults (Windows Credential Manager / macOS Keychain).</li>
          </ul>
        </section>

        <section className="space-y-4">
          <h2 className="text-xl font-semibold">4. Data Storage and Security</h2>
          <p className="leading-relaxed text-muted-foreground">
            CashPilot operates under a local-first, zero-trust security architecture. Stored data is sealed with AES-256 encryption. We do not sell, rent, or monetize your financial data to advertisers, data brokers, or third-party lenders.
          </p>
        </section>

        <section className="space-y-4">
          <h2 className="text-xl font-semibold">5. User Control & Data Deletion</h2>
          <p className="leading-relaxed text-muted-foreground">
            You maintain full sovereignty over your data at all times. Disconnecting your mailbox in the <strong>Bank emails</strong> dashboard instantly revokes the access token, purges stored credentials from your device vault, and deletes local cached records.
          </p>
        </section>

        <section className="space-y-4 border-t pt-6">
          <h2 className="text-xl font-semibold">6. Contact</h2>
          <p className="leading-relaxed text-muted-foreground">
            If you have questions regarding this Privacy Policy or your data, please contact the developer via GitHub at{' '}
            <a href="https://github.com/SamJU25/CashPilot" target="_blank" rel="noreferrer" className="underline underline-offset-4">
              github.com/SamJU25/CashPilot
            </a>.
          </p>
        </section>
      </div>
    </div>
  );
}
