import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { Shield, Lock, EyeOff, CheckCircle2, XCircle, FileText } from "lucide-react";

export default function SecurityPage() {
  return (
    <div className="min-h-screen bg-bg text-ink flex flex-col">
      <Navbar />

      <main className="flex-1 py-12 sm:py-16">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 space-y-12">
          {/* Header */}
          <div className="text-center space-y-3">
            <span className="cnl-kicker text-xs font-semibold text-accent uppercase tracking-wider">
              Privacy by Design
            </span>
            <h1 className="text-4xl font-serif font-normal tracking-tight text-ink sm:text-5xl">
              Security & DPDP Architecture
            </h1>
            <p className="text-sm text-mute max-w-2xl mx-auto leading-relaxed">
              Float is engineered from the ground up for strict privacy, client-side PII masking, and deterministic read-only operations.
            </p>
          </div>

          {/* What Float Reads vs What Float NEVER Touches */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* What Float Reads */}
            <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-4">
              <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
                <CheckCircle2 className="h-5 w-5" />
                <h3 className="text-base font-serif font-semibold text-ink">What Float Processes:</h3>
              </div>
              <ul className="space-y-2.5 text-xs text-mute">
                <li className="flex items-start gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" />
                  <span><strong>Bank Statement CSVs:</strong> Transaction amounts, dates, and debit/credit categories to compute cash flow.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" />
                  <span><strong>Scam Inquiries:</strong> Suspicious SMS / message text pasted into the scam checker.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" />
                  <span><strong>Financial Questions:</strong> User queries to retrieve matching regulatory clauses.</span>
                </li>
              </ul>
            </div>

            {/* What Float NEVER Touches */}
            <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-4">
              <div className="flex items-center gap-2 text-rose-700 dark:text-rose-400">
                <XCircle className="h-5 w-5" />
                <h3 className="text-base font-serif font-semibold text-ink">What Float NEVER Touches:</h3>
              </div>
              <ul className="space-y-2.5 text-xs text-mute">
                <li className="flex items-start gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-rose-500 mt-1.5 shrink-0" />
                  <span><strong>Net Banking Credentials / Passwords:</strong> Float never requests or accepts banking logins.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-rose-500 mt-1.5 shrink-0" />
                  <span><strong>OTPs / PINs:</strong> We never read, store, or ask for one-time passwords or UPI PINs.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-rose-500 mt-1.5 shrink-0" />
                  <span><strong>Write-access to bank accounts:</strong> Float is read-only. We cannot move funds or execute transactions.</span>
                </li>
              </ul>
            </div>
          </div>

          {/* Core Guarantees */}
          <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-6">
            <h3 className="text-lg font-serif font-medium text-ink">Our Core AI & Data Guarantees</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="space-y-1.5 p-4 rounded-2xl bg-soft/30 border border-line">
                <Shield className="h-5 w-5 text-accent" />
                <h4 className="text-xs font-bold text-ink">PII Masking</h4>
                <p className="text-[11px] text-mute">All account numbers, phone numbers, and names are stripped before external LLM queries.</p>
              </div>
              <div className="space-y-1.5 p-4 rounded-2xl bg-soft/30 border border-line">
                <EyeOff className="h-5 w-5 text-accent" />
                <h4 className="text-xs font-bold text-ink">Zero Training on User Data</h4>
                <p className="text-[11px] text-mute">Your data is never used to train or fine-tune public foundation models.</p>
              </div>
              <div className="space-y-1.5 p-4 rounded-2xl bg-soft/30 border border-line">
                <Lock className="h-5 w-5 text-accent" />
                <h4 className="text-xs font-bold text-ink">DPDP Right to Erasure</h4>
                <p className="text-[11px] text-mute">Delete your entire conversation history at any time from Settings in one click.</p>
              </div>
            </div>
          </div>

          {/* Grievance Officer Contact Placeholder */}
          <div className="rounded-2xl border border-line bg-soft/30 p-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h4 className="text-xs font-bold text-ink uppercase tracking-wider">DPDP Grievance Officer</h4>
              <p className="text-xs text-mute mt-0.5">
                Designated officer for data privacy inquiries and DPDP compliance under Indian law.
              </p>
            </div>
            <div className="text-xs text-mute font-mono bg-card px-3 py-2 rounded-lg border border-line">
              grievance@float.internal
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
