"use client";

import { useState, useEffect } from "react";
import { Shield, CheckCircle2, AlertCircle } from "lucide-react";
import AppShell from "@/components/AppShell";
import PlanTabs from "@/components/PlanTabs";
import { getApiClient } from "@/lib/api";
import type { EmergencyFundResponse } from "@float/api-client";
import { formatINR } from "@/lib/i18n";

export default function EmergencyFundPage() {
  const [data, setData] = useState<EmergencyFundResponse | null>(null);
  const [targetMonths, setTargetMonths] = useState("6");
  const [savedInr, setSavedInr] = useState("0");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [hideAmounts, setHideAmounts] = useState(false);

  const api = getApiClient();

  useEffect(() => {
    setHideAmounts(localStorage.getItem("float_hide_amounts") === "true");
    const onPrivacy = (e: any) => {
      if (typeof e.detail?.hide === "boolean") setHideAmounts(e.detail.hide);
    };
    window.addEventListener("float_privacy_toggle", onPrivacy);
    return () => window.removeEventListener("float_privacy_toggle", onPrivacy);
  }, []);

  async function loadEmergencyFund(preserveUnsaved = false) {
    setLoading(true);
    setError(null);
    try {
      const res = await api.plan.getEmergencyFund();
      setData(res);
      if (!preserveUnsaved) {
        setTargetMonths(String(res.target_months));
        setSavedInr(String(res.saved_paise / 100));
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load emergency fund.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadEmergencyFund();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setStatusMsg(null);
    try {
      const res = await api.plan.updateEmergencyFund({
        target_months: Math.min(36, Math.max(0, Number(targetMonths) || 0)),
        saved_paise: Math.max(0, Math.round((Number(savedInr) || 0) * 100)),
        expected_version: data?.version ?? 0,
      });
      setData(res);
      setStatusMsg("Emergency fund target updated.");
    } catch (err: any) {
      if (err?.status === 409 || /conflict|changed elsewhere/i.test(err?.message || "")) {
        await loadEmergencyFund(true);
        setError("Emergency fund settings were changed elsewhere. Latest version reloaded — your unsaved edits remain.");
      } else {
        setError(err?.message || "Failed to update emergency fund.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto space-y-6 pb-16">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <span className="cnl-kicker">Plan</span>
            <h1 className="text-2xl sm:text-3xl font-serif font-normal text-ink mt-1">Emergency Fund</h1>
            <p className="text-xs sm:text-sm text-mute mt-1">
              Target months (3–6 default) multiplied by your essential expenses from Needs + active essential recurring bills.
            </p>
          </div>
          <PlanTabs />
        </div>

        {error && (
          <div role="alert" className="flex items-center gap-2 rounded-xl border border-red-300 bg-red-50 dark:bg-red-950/30 p-3 text-xs text-red-700 dark:text-red-300">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}
        {statusMsg && (
          <div role="status" className="flex items-center gap-2 rounded-xl border border-emerald-300 bg-emerald-50 dark:bg-emerald-950/30 p-3 text-xs text-emerald-800 dark:text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>{statusMsg}</span>
          </div>
        )}

        {loading ? (
          <div data-testid="ef-skeleton" className="h-24 rounded-3xl bg-soft animate-pulse" />
        ) : (
          data && (
            <>
              <section data-testid="ef-summary" className="rounded-3xl border border-line bg-card p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Shield className="h-5 w-5 text-accent" />
                    <h2 className="text-base font-serif font-medium text-ink">
                      Target: {formatINR(data.target_amount_paise / 100, { hideAmount: hideAmounts })}
                    </h2>
                  </div>
                  <span className="text-sm font-semibold text-ink">{data.progress_pct}%</span>
                </div>
                <div className="h-2.5 w-full rounded-full bg-soft overflow-hidden">
                  <div style={{ width: `${data.progress_pct}%` }} className="h-full bg-accent transition-all" />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs text-mute">
                  <div>
                    Essential monthly: <span className="font-semibold text-ink">{formatINR(data.essential_monthly_paise / 100, { hideAmount: hideAmounts })}</span>
                  </div>
                  <div>
                    Effective saved (reserve + liquid): <span className="font-semibold text-ink">{formatINR(data.effective_saved_paise / 100, { hideAmount: hideAmounts })}</span>
                  </div>
                  <div>
                    {data.over_saved_paise > 0
                      ? `Surplus: ${formatINR(data.over_saved_paise / 100, { hideAmount: hideAmounts })}`
                      : `Remaining: ${formatINR(data.remaining_paise / 100, { hideAmount: hideAmounts })}`}
                  </div>
                </div>
              </section>

              <form onSubmit={handleSave} className="rounded-3xl border border-line bg-card p-6 space-y-4">
                <h2 className="text-base font-serif font-medium text-ink">Configure Target Months &amp; Dedicated Reserve</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="ef-months" className="block text-xs font-medium text-ink mb-1">Target Months (0–36)</label>
                    <input id="ef-months" type="number" min={0} max={36} value={targetMonths} onChange={(e) => setTargetMonths(e.target.value)} className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink" />
                  </div>
                  <div>
                    <label htmlFor="ef-saved" className="block text-xs font-medium text-ink mb-1">Dedicated Emergency Reserve (INR)</label>
                    <input id="ef-saved" type="number" min={0} value={savedInr} onChange={(e) => setSavedInr(e.target.value)} className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink" />
                  </div>
                </div>
                <div className="flex justify-end">
                  <button type="submit" disabled={saving} data-testid="save-ef-btn" className="rounded-xl bg-ink px-4 py-2 text-xs font-semibold text-bg hover:opacity-90 disabled:opacity-50">
                    {saving ? "Saving..." : "Save Emergency Fund"}
                  </button>
                </div>
              </form>
            </>
          )
        )}
      </div>
    </AppShell>
  );
}
