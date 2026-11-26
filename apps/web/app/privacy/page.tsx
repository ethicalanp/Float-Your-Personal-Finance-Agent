import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-bg text-ink flex flex-col">
      <Navbar />

      <main className="flex-1 py-12 sm:py-16">
        <div className="mx-auto max-w-3xl px-4 sm:px-6 space-y-8">
          <div>
            <span className="cnl-kicker text-xs font-semibold text-accent uppercase tracking-wider">
              Data Protection
            </span>
            <h1 className="text-3xl font-serif font-normal tracking-tight text-ink sm:text-4xl">
              Privacy Notice (DPDP Act, 2023)
            </h1>
            <p className="mt-1 text-xs text-mute">Last updated: November 2026</p>
          </div>

          <div className="space-y-6 text-xs text-mute leading-relaxed">
            <section className="space-y-2">
              <h2 className="text-sm font-bold text-ink">1. Data Fiduciary Notice</h2>
              <p>
                In compliance with the Digital Personal Data Protection Act, 2023 (DPDP Act), Float acts as the Data Fiduciary for personal data processed when you utilize our personal finance, fraud protection, and AI assistant services.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-sm font-bold text-ink">2. Purpose of Collection</h2>
              <p>
                We collect and process bank statement transactions solely to compute cash-flow statistics and assess indicative credit readiness. We process scam report text solely to identify fraud patterns and provide protective recommendations.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-sm font-bold text-ink">3. Client-Side PII Masking</h2>
              <p>
                Before queries are dispatched to any external language model, personal identifiers (such as account numbers, phone numbers, and full names) are deterministically masked.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-sm font-bold text-ink">4. Right to Erasure & Grievances</h2>
              <p>
                You retain the right to withdraw AI processing consent and permanently delete all conversation history via the Settings screen. For privacy concerns or formal grievances, reach out to: <strong>grievance@float.internal</strong>.
              </p>
            </section>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
