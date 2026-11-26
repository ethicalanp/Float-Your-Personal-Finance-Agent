"use client";

import { useState } from "react";
import Link from "next/link";
import {
  CreditCard,
  CheckCircle2,
  AlertTriangle,
  Info,
  ArrowRight,
  TrendingUp,
  FileText,
  ShieldCheck,
} from "lucide-react";
import AppShell from "@/components/AppShell";
import { getApiClient } from "@/lib/api";
import type { BorrowAssessResponse } from "@float/api-client";

export default function BorrowPage() {
  const [assessment, setAssessment] = useState<BorrowAssessResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorStatus, setErrorStatus] = useState<"unavailable" | "insufficient_data" | "generic" | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const api = getApiClient();

  async function handleAssess() {
    setLoading(true);
    setErrorStatus(null);
    setErrorMessage(null);

    try {
      const res = await api.borrow.assess();
      setAssessment(res);
    } catch (err: any) {
      if (err.status === 503 || err.code === "SERVICE_UNAVAILABLE") {
        setErrorStatus("unavailable");
        setErrorMessage("Borrow assessment service is currently undergoing routine maintenance. Please check back shortly.");
      } else if (err.status === 400 && err.message?.toLowerCase().includes("insufficient")) {
        setErrorStatus("insufficient_data");
        setErrorMessage("Insufficient transaction history. Please upload at least 30 days of bank statements.");
      } else {
        setErrorStatus("generic");
        setErrorMessage(err.message || "Could not complete assessment at this time.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <span className="cnl-kicker text-xs font-semibold text-accent uppercase tracking-wider">
            Borrow Readiness
          </span>
          <h1 className="text-3xl font-serif font-normal text-ink sm:text-4xl">
            Loan & Credit Readiness
          </h1>
          <p className="mt-1 text-xs text-mute">
            Objective evaluation of your cash-flow stability and borrowing capacity before you apply with banks.
          </p>
        </div>

        {/* Assessment Trigger Card */}
        <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <h2 className="text-lg font-serif font-medium text-ink">Check Your Indicative Readiness</h2>
              <p className="text-xs text-mute max-w-xl">
                We analyze your recurring income consistency, expense-to-inflow ratio, and cash flow volatility without affecting your CIBIL score.
              </p>
            </div>
            <button
              onClick={handleAssess}
              disabled={loading}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-ink px-5 py-3 text-xs font-semibold text-bg transition-all hover:opacity-90 disabled:opacity-50 shrink-0"
            >
              <CreditCard className="h-4 w-4" />
              <span>{loading ? "Evaluating Cash Flow..." : "Assess My Readiness"}</span>
            </button>
          </div>
        </div>

        {/* State: Loading Skeleton */}
        {loading && (
          <div data-testid="borrow-skeleton" className="rounded-3xl border border-line bg-card p-6 sm:p-8 animate-pulse space-y-4">
            <div className="h-6 w-1/3 bg-soft rounded" />
            <div className="h-16 w-full bg-soft rounded" />
            <div className="h-24 w-full bg-soft rounded" />
          </div>
        )}

        {/* State: Service Unavailable (503) */}
        {errorStatus === "unavailable" && (
          <div className="rounded-3xl border border-amber-200 bg-amber-50/50 p-6 sm:p-8 dark:border-amber-900/50 dark:bg-amber-950/20">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/10 text-amber-700 dark:text-amber-400">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-amber-950 dark:text-amber-200">
                  Assessment Model Temporarily Unavailable
                </h3>
                <p className="text-xs text-amber-800 dark:text-amber-300 leading-relaxed">
                  {errorMessage}
                </p>
                <div className="pt-2">
                  <button
                    onClick={handleAssess}
                    className="rounded-lg border border-amber-300 bg-white px-3.5 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-50 dark:border-amber-800 dark:bg-amber-900/40 dark:text-amber-200"
                  >
                    Try Again
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* State: Insufficient Data (400) */}
        {errorStatus === "insufficient_data" && (
          <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-soft text-mute">
                <FileText className="h-5 w-5" />
              </div>
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-ink">More Transaction History Needed</h3>
                <p className="text-xs text-mute leading-relaxed max-w-xl">
                  {errorMessage}
                </p>
                <Link
                  href="/home"
                  className="inline-flex items-center gap-1.5 rounded-xl bg-ink px-4 py-2 text-xs font-semibold text-bg hover:opacity-90 transition-all"
                >
                  <span>Upload Bank Statement</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            </div>
          </div>
        )}

        {/* State: Generic Error */}
        {errorStatus === "generic" && (
          <div className="rounded-3xl border border-red-200 bg-red-50/50 p-6 text-xs text-red-800 dark:border-red-900/50 dark:bg-red-950/20 dark:text-red-300">
            {errorMessage}
          </div>
        )}

        {/* Assessment Result */}
        {assessment && (
          <div className="space-y-6">
            <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-line pb-6">
                <div>
                  <span className="text-xs font-semibold text-mute uppercase tracking-wider">
                    Assessed Readiness Tier
                  </span>
                  <h3 className="text-2xl font-serif font-medium text-ink capitalize mt-1">
                    {assessment.readiness_band}
                  </h3>
                </div>
                <div className="flex items-center gap-2">
                  <div className="text-right">
                    <span className="text-[10px] text-faint uppercase font-bold tracking-wider">Stability Score</span>
                    <div className="text-xl font-bold font-mono text-ink">
                      {Math.round((assessment.readiness_score ?? 0) * 100)} / 100
                    </div>
                  </div>
                </div>
              </div>

              {/* Contributing Factors & Reasons */}
              <div className="space-y-3">
                <h4 className="text-xs font-semibold text-mute uppercase tracking-wider">
                  Key Evaluation Factors (Tree SHAP)
                </h4>
                <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                  {(assessment.positive_factors || []).map((reason: string, idx: number) => (
                    <div
                      key={idx}
                      className="flex items-start gap-2.5 rounded-xl border border-line bg-soft/30 p-3 text-xs text-ink"
                    >
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 mt-0.5" />
                      <span>{reason}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Statutory Indicative Disclaimer */}
              <div className="rounded-2xl border border-line bg-soft/40 p-4 text-xs text-mute space-y-1">
                <div className="flex items-center gap-1.5 font-semibold text-ink">
                  <ShieldCheck className="h-4 w-4 text-accent" />
                  <span>Mandatory Statutory Notice</span>
                </div>
                <p className="text-[11px] leading-relaxed text-faint">
                  {assessment.legal_disclaimer}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
