"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck, ArrowRight, Lock, CheckCircle2, AlertCircle } from "lucide-react";
import AppShell from "@/components/AppShell";

export default function ConsentPage() {
  const router = useRouter();
  const [granted, setGranted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadConsent() {
      try {
        const res = await fetch("/api/auth/me");
        if (res.ok) {
          const data = await res.json();
          setGranted(Boolean(data.consent?.ai_data_processing_consent));
        }
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    }
    loadConsent();
  }, []);

  async function handleToggle(grant: boolean) {
    setError(null);
    setUpdating(true);
    try {
      const res = await fetch("/api/auth/consent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ai_data_processing_consent: grant,
          consent_version: "v1.0",
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error?.message || "Failed to update consent");
      }
      setGranted(grant);
      if (grant) {
        router.push("/assistant");
      }
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred");
    } finally {
      setUpdating(false);
    }
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-2xl">
        <div className="rounded-3xl border border-line bg-card p-6 sm:p-10 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/10 text-accent">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <span className="cnl-kicker text-xs font-semibold text-accent uppercase tracking-wider">
                DPDP Act 2023 Compliance
              </span>
              <h1 className="text-2xl font-serif font-normal text-ink sm:text-3xl">
                AI Data Processing Consent
              </h1>
            </div>
          </div>

          <p className="mt-4 text-sm leading-relaxed text-mute">
            Float uses artificial intelligence to analyze financial inquiries, detect scam patterns, and retrieve official regulatory guidance (RBI, I4C, NPCI). In accordance with the Digital Personal Data Protection Act, 2023, we require your explicit permission to process your questions and transaction context.
          </p>

          <div className="mt-6 space-y-3 rounded-2xl border border-line bg-soft/40 p-5">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-ink">
              What Float does with this consent:
            </h3>
            <ul className="space-y-2 text-xs text-mute">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600 mt-0.5" />
                <span>Masks personally identifiable information (names, account numbers, phones) before analysis.</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600 mt-0.5" />
                <span>Provides grounded answers citing official regulatory notices, circulars, and helplines.</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600 mt-0.5" />
                <span>Never sells, trades, or trains public foundation models on your private financial data.</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600 mt-0.5" />
                <span>You can revoke this consent or purge conversation history at any time from Settings.</span>
              </li>
            </ul>
          </div>

          {error && (
            <div className="mt-4 flex items-center gap-2 rounded-xl bg-red-50 p-4 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-t border-line pt-6">
            <div className="flex items-center gap-2 text-xs text-mute">
              <Lock className="h-3.5 w-3.5" />
              <span>Status: {granted ? "Granted" : "Not Granted"}</span>
            </div>

            <div className="flex items-center gap-3">
              {granted ? (
                <button
                  onClick={() => handleToggle(false)}
                  disabled={updating}
                  className="rounded-xl border border-line px-4 py-2.5 text-xs font-medium text-mute hover:bg-soft hover:text-ink disabled:opacity-50"
                >
                  {updating ? "Updating..." : "Withdraw Consent"}
                </button>
              ) : (
                <button
                  onClick={() => handleToggle(true)}
                  disabled={updating}
                  className="flex items-center gap-2 rounded-xl bg-accent px-5 py-2.5 text-xs font-semibold text-white hover:bg-accent/90 disabled:opacity-50 transition-all shadow-sm"
                >
                  <span>{updating ? "Granting..." : "Accept & Enable Assistant"}</span>
                  <ArrowRight className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
