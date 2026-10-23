import Link from 'next/link';

export const metadata = {
  title: 'Terms of Service — CashPilot',
  description: 'CashPilot Terms of Service',
};

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-background px-6 py-16 text-foreground">
      <div className="mx-auto max-w-3xl space-y-8">
        <header className="border-b pb-6">
          <Link href="/" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground">
            ← Back to CashPilot
          </Link>
          <h1 className="mt-4 font-display text-3xl font-bold tracking-tight">Terms of Service</h1>
          <p className="mt-2 text-sm text-muted-foreground">Effective Date: October 24, 2026</p>
        </header>

        <section className="space-y-4">
          <h2 className="text-xl font-semibold">1. Acceptance of Terms</h2>
          <p className="leading-relaxed text-muted-foreground">
            By accessing or using CashPilot (&quot;the Service&quot;), you agree to be bound by these Terms of Service. If you do not agree to these terms, do not access or use the Service.
          </p>
        </section>

        <section className="space-y-4">
          <h2 className="text-xl font-semibold">2. Purpose of Service</h2>
          <p className="leading-relaxed text-muted-foreground">
            CashPilot provides automated financial diagnostics, runway estimations, working capital metrics, and transactional reconciliation for small and medium enterprises. CashPilot does not provide certified accounting, legal, or licensed credit underwriting advice.
          </p>
        </section>

        <section className="space-y-4">
          <h2 className="text-xl font-semibold">3. Third-Party Integrations</h2>
          <p className="leading-relaxed text-muted-foreground">
            When connecting third-party services such as Google, Microsoft, or bank statement feeds, you authorize CashPilot to access relevant transactional records strictly in accordance with our Privacy Policy.
          </p>
        </section>

        <section className="space-y-4">
          <h2 className="text-xl font-semibold">4. Limitation of Liability</h2>
          <p className="leading-relaxed text-muted-foreground">
            CashPilot is provided &quot;as is&quot; without warranties of any kind. In no event shall CashPilot or its contributors be liable for any indirect, incidental, or consequential damages arising from the use or inability to use the Service.
          </p>
        </section>

        <section className="space-y-4 border-t pt-6">
          <h2 className="text-xl font-semibold">5. Inquiries</h2>
          <p className="leading-relaxed text-muted-foreground">
            For questions regarding these Terms, visit{' '}
            <a href="https://github.com/SamJU25/CashPilot" target="_blank" rel="noreferrer" className="underline underline-offset-4">
              github.com/SamJU25/CashPilot
            </a>.
          </p>
        </section>
      </div>
    </div>
  );
}
