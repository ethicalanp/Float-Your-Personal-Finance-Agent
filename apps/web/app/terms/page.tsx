import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-bg text-ink flex flex-col">
      <Navbar />

      <main className="flex-1 py-12 sm:py-16">
        <div className="mx-auto max-w-3xl px-4 sm:px-6 space-y-8">
          <div>
            <span className="cnl-kicker text-xs font-semibold text-accent uppercase tracking-wider">
              Legal Terms
            </span>
            <h1 className="text-3xl font-serif font-normal tracking-tight text-ink sm:text-4xl">
              Terms of Service
            </h1>
            <p className="mt-1 text-xs text-mute">Last updated: November 2026</p>
          </div>

          <div className="space-y-6 text-xs text-mute leading-relaxed">
            <section className="space-y-2">
              <h2 className="text-sm font-bold text-ink">1. Acceptance of Terms</h2>
              <p>
                By creating an account or accessing the Float service, you agree to these Terms of Service. Float is an educational personal finance management and scam-awareness platform designed for users in India.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-sm font-bold text-ink">2. Not Financial or Legal Advice</h2>
              <p>
                Float is not an investment advisor registered with SEBI, a lender registered with the RBI, or a law firm. All cash-flow insights, loan readiness scores, and regulatory citations are provided strictly for educational and indicative informational purposes.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-sm font-bold text-ink">3. Read-Only Service</h2>
              <p>
                Float operates as a read-only tool. Float never executes financial transactions, initiates payments, moves money, or applies for loans on your behalf.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-sm font-bold text-ink">4. Emergency Cyber Fraud Guidance</h2>
              <p>
                In the event of active financial cyber fraud, users must contact the National Cybercrime Reporting Portal helpline directly at <strong>1930</strong> or register a complaint at <strong>cybercrime.gov.in</strong>. Float is not an emergency dispatch or law enforcement entity.
              </p>
            </section>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
