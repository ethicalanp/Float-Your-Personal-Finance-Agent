"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Check, Scissors, Sparkles, X } from "lucide-react";
import AppShell from "@/components/AppShell";
import PlanTabs from "@/components/PlanTabs";
import { getApiClient } from "@/lib/api";
import type { SubscriptionLeaksResponse } from "@float/api-client";
import { formatINR } from "@/lib/i18n";

const RULE_LABELS: Record<string, string> = {
  duplicate: "Duplicate",
  price_increase: "Price increase",
  small_recurring: "Small recurring",
  annual_renewal: "Annual renewal",
  trial_to_paid: "Trial to paid",
};

export default function PlanSubscriptionsPage() {
  const [hideAmounts, setHideAmounts] = useState(false);
  const [data, setData] = useState<SubscriptionLeaksResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const api = getApiClient();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.plan.getSubscriptionLeaks();
      setData(res);
    } catch (err: any) {
      setError(err?.message || "Failed to load subscription leaks.");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    setHideAmounts(localStorage.getItem("float_hide_amounts") === "true");
    const onPrivacy = (e: any) => {
      if (typeof e.detail?.hide === "boolean") setHideAmounts(e.detail.hide);
    };
    window.addEventListener("float_privacy_toggle", onPrivacy);
    load();
    return () => window.removeEventListener("float_privacy_toggle", onPrivacy);
  }, [load]);

  async function markDecision(leakKey: string, decision: "keep" | "cancel") {
    setSavingKey(leakKey);
    setError(null);
    try {
      const updated = await api.plan.setSubscriptionLeakDecision(leakKey, decision);
      setData(updated);
    } catch (err: any) {
      setError(err?.message || "Could not save your decision.");
    } finally {
      setSavingKey(null);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6 max-w-5xl mx-auto">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-ink tracking-tight">Subscriptions & leak finder</h1>
            <p className="text-sm text-mute mt-1">
              Spot duplicate charges, price hikes, trial conversions, and small recurring leaks. Mark Keep or Cancel to estimate yearly savings (no automatic cancellations).
            </p>
          </div>
          <PlanTabs tabsLabel="Plan sections" budgetLabel="Budget" recurringLabel="Recurring & bills" />
        </div>

        {error && (
          <div role="alert" className="flex items-center gap-2 rounded-xl border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="rounded-2xl border border-line bg-card p-4">
            <p className="text-xs font-medium text-mute">Detected leaks</p>
            <p className="text-2xl font-bold text-ink mt-1" data-testid="leaks-count">
              {loading ? "—" : data?.total_leaks ?? 0}
            </p>
          </div>
          <div className="rounded-2xl border border-line bg-card p-4">
            <p className="text-xs font-medium text-mute">Estimated yearly savings (Cancel)</p>
            <p className="text-2xl font-bold text-ok mt-1" data-testid="estimated-yearly-savings">
              {loading
                ? "—"
                : formatINR((data?.estimated_yearly_savings_paise ?? 0) / 100, {
                    hideAmount: hideAmounts,
                    compact: true,
                  })}
            </p>
          </div>
          <div className="rounded-2xl border border-line bg-card p-4">
            <p className="text-xs font-medium text-mute">Potential yearly savings</p>
            <p className="text-2xl font-bold text-ink mt-1" data-testid="potential-yearly-savings">
              {loading
                ? "—"
                : formatINR((data?.potential_yearly_savings_paise ?? 0) / 100, {
                    hideAmount: hideAmounts,
                    compact: true,
                  })}
            </p>
          </div>
        </div>

        <section id="panel-subscriptions" role="tabpanel" aria-labelledby="tab-subscriptions" className="space-y-3">
          {loading ? (
            <div className="rounded-2xl border border-line bg-card p-8 text-center text-sm text-mute">
              Scanning recurring items and transactions…
            </div>
          ) : !data || data.leaks.length === 0 ? (
            <div className="rounded-2xl border border-line bg-card p-8 text-center space-y-2" data-testid="leaks-empty">
              <Sparkles className="h-8 w-8 text-accent mx-auto" />
              <p className="text-base font-semibold text-ink">No subscription leaks detected</p>
              <p className="text-sm text-mute max-w-md mx-auto">
                Add recurring commitments or upload a bank statement CSV to detect duplicate subscriptions, price increases, or trial-to-paid charges.
              </p>
            </div>
          ) : (
            data.leaks.map((leak) => (
              <div
                key={leak.leak_key}
                data-testid={`leak-card-${leak.leak_key}`}
                className="rounded-2xl border border-line bg-card p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
              >
                <div className="space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Scissors className="h-4 w-4 text-accent shrink-0" />
                    <h2 className="text-base font-semibold text-ink">{leak.merchant}</h2>
                    {leak.rules_triggered.map((rule) => (
                      <span
                        key={rule}
                        className="rounded-full bg-soft border border-line px-2.5 py-0.5 text-xs font-medium text-ink"
                      >
                        {RULE_LABELS[rule] || rule}
                      </span>
                    ))}
                  </div>
                  <p className="text-sm text-mute">{leak.explanation}</p>
                  <p className="text-xs text-mute">
                    Monthly:{" "}
                    <span className="font-semibold text-ink">
                      {formatINR(leak.monthly_amount_paise / 100, { hideAmount: hideAmounts })}
                    </span>{" "}
                    · Annual:{" "}
                    <span className="font-semibold text-ink">
                      {formatINR(leak.annual_cost_paise / 100, { hideAmount: hideAmounts, compact: true })}
                    </span>
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    disabled={savingKey === leak.leak_key}
                    onClick={() => markDecision(leak.leak_key, "keep")}
                    data-testid={`leak-keep-${leak.leak_key}`}
                    className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold border transition-colors ${
                      leak.decision === "keep"
                        ? "bg-ok/15 border-ok text-ok"
                        : "bg-soft border-line text-ink hover:border-ink/40"
                    }`}
                  >
                    <Check className="h-3.5 w-3.5" />
                    Keep
                  </button>
                  <button
                    type="button"
                    disabled={savingKey === leak.leak_key}
                    onClick={() => markDecision(leak.leak_key, "cancel")}
                    data-testid={`leak-cancel-${leak.leak_key}`}
                    className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold border transition-colors ${
                      leak.decision === "cancel"
                        ? "bg-bad/15 border-bad text-bad"
                        : "bg-soft border-line text-ink hover:border-bad/50"
                    }`}
                  >
                    <X className="h-3.5 w-3.5" />
                    Cancel
                  </button>
                </div>
              </div>
            ))
          )}
        </section>
      </div>
    </AppShell>
  );
}
