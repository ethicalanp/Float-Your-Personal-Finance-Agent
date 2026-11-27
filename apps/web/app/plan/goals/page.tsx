"use client";

import { useState, useEffect, useRef } from "react";
import { Target, Plus, Trash2, ArrowUp, ArrowDown, AlertTriangle, AlertCircle, CheckCircle2 } from "lucide-react";
import AppShell from "@/components/AppShell";
import PlanTabs from "@/components/PlanTabs";
import { getApiClient } from "@/lib/api";
import type { GoalItemOut, GoalsOverviewResponse } from "@float/api-client";
import { formatINR, formatISTDate } from "@/lib/i18n";

export default function GoalsPage() {
  const [overview, setOverview] = useState<GoalsOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [hideAmounts, setHideAmounts] = useState(false);

  const [name, setName] = useState("");
  const [targetInr, setTargetInr] = useState("");
  const [savedInr, setSavedInr] = useState("0");
  const [targetDate, setTargetDate] = useState(() => {
    const d = new Date();
    d.setMonth(d.getMonth() + 6);
    return d.toISOString().slice(0, 10);
  });
  const [priority, setPriority] = useState("1");
  const [submitting, setSubmitting] = useState(false);
  const isSubmitting = useRef(false);

  const api = getApiClient();

  useEffect(() => {
    setHideAmounts(localStorage.getItem("float_hide_amounts") === "true");
    const onPrivacy = (e: any) => {
      if (typeof e.detail?.hide === "boolean") setHideAmounts(e.detail.hide);
    };
    window.addEventListener("float_privacy_toggle", onPrivacy);
    return () => window.removeEventListener("float_privacy_toggle", onPrivacy);
  }, []);

  async function loadGoals() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.plan.getGoals();
      setOverview(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load goals.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadGoals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreateGoal(e: React.FormEvent) {
    e.preventDefault();
    if (isSubmitting.current) return;
    const tgtPaise = Math.round((Number(targetInr) || 0) * 100);
    const savPaise = Math.max(0, Math.round((Number(savedInr) || 0) * 100));
    if (!name.trim() || tgtPaise <= 0) {
      setError("Enter a goal name and positive INR target amount.");
      return;
    }
    isSubmitting.current = true;
    setSubmitting(true);
    setError(null);
    setStatusMsg(null);
    try {
      const data = await api.plan.createGoal({
        name: name.trim(),
        target_amount_paise: tgtPaise,
        saved_paise: savPaise,
        target_date: targetDate,
        priority: Math.max(1, Number(priority) || 1),
      });
      setOverview(data);
      setName("");
      setTargetInr("");
      setSavedInr("0");
      setStatusMsg("Goal added.");
    } catch (err: any) {
      setError(err?.message || "Failed to add goal.");
    } finally {
      setSubmitting(false);
      isSubmitting.current = false;
    }
  }

  async function handleReprioritize(g: GoalItemOut, delta: number) {
    const nextPriority = Math.max(1, g.priority + delta);
    setError(null);
    setStatusMsg(null);
    try {
      const data = await api.plan.updateGoal(g.id, {
        priority: nextPriority,
        expected_version: g.version,
      });
      setOverview(data);
      setStatusMsg(`Updated priority for ${g.name}.`);
    } catch (err: any) {
      if (err?.status === 409 || /conflict|changed elsewhere/i.test(err?.message || "")) {
        await loadGoals();
        setError("This goal was changed elsewhere. Latest version reloaded.");
      } else {
        setError(err?.message || "Failed to update goal.");
      }
    }
  }

  async function handleDelete(id: string) {
    setError(null);
    setStatusMsg(null);
    try {
      const data = await api.plan.deleteGoal(id);
      setOverview(data);
      setStatusMsg("Goal deleted.");
    } catch (err: any) {
      setError(err?.message || "Failed to delete goal.");
    }
  }

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto space-y-6 pb-16">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <span className="cnl-kicker">Plan</span>
            <h1 className="text-2xl sm:text-3xl font-serif font-normal text-ink mt-1">Savings Goals</h1>
            <p className="text-xs sm:text-sm text-mute mt-1">
              Set target amounts and dates, check feasibility against your budget&apos;s savings share, and prioritize.
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

        {overview?.has_allocation_conflict && (
          <div
            role="alert"
            data-testid="goals-conflict-banner"
            className="rounded-2xl border border-amber-400/50 bg-amber-500/10 p-4 flex items-start gap-3 text-xs text-ink"
          >
            <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold">Goals exceed your monthly budget savings share</div>
              <p className="text-mute mt-0.5">
                Suggested monthly savings ({formatINR(overview.total_suggested_monthly_paise / 100, { hideAmount: hideAmounts })})
                exceeds your budget&apos;s savings allocation ({formatINR((overview.budget_savings_paise || 0) / 100, { hideAmount: hideAmounts })})
                by {formatINR(overview.shortfall_paise / 100, { hideAmount: hideAmounts })}. Use the priority controls below to rank what comes first.
              </p>
            </div>
          </div>
        )}

        <form onSubmit={handleCreateGoal} className="rounded-3xl border border-line bg-card p-6 space-y-4">
          <div className="flex items-center gap-2">
            <Plus className="h-4 w-4 text-accent" />
            <h2 className="text-base font-serif font-medium text-ink">Add Savings Goal</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
            <div>
              <label htmlFor="goal-name" className="block text-xs font-medium text-ink mb-1">Goal Name</label>
              <input id="goal-name" type="text" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Laptop / Home Deposit" className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink" />
            </div>
            <div>
              <label htmlFor="goal-target" className="block text-xs font-medium text-ink mb-1">Target (INR)</label>
              <input id="goal-target" type="number" required min={1} value={targetInr} onChange={(e) => setTargetInr(e.target.value)} placeholder="60000" className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink" />
            </div>
            <div>
              <label htmlFor="goal-saved" className="block text-xs font-medium text-ink mb-1">Saved So Far (INR)</label>
              <input id="goal-saved" type="number" min={0} value={savedInr} onChange={(e) => setSavedInr(e.target.value)} className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink" />
            </div>
            <div>
              <label htmlFor="goal-date" className="block text-xs font-medium text-ink mb-1">Target Date</label>
              <input id="goal-date" type="date" required value={targetDate} onChange={(e) => setTargetDate(e.target.value)} className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink" />
            </div>
            <div>
              <label htmlFor="goal-priority" className="block text-xs font-medium text-ink mb-1">Priority (1 = Highest)</label>
              <input id="goal-priority" type="number" min={1} value={priority} onChange={(e) => setPriority(e.target.value)} className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink" />
            </div>
          </div>
          <div className="flex justify-end">
            <button type="submit" disabled={submitting} data-testid="add-goal-btn" className="rounded-xl bg-ink px-4 py-2 text-xs font-semibold text-bg hover:opacity-90 disabled:opacity-50">
              {submitting ? "Adding..." : "Add Goal"}
            </button>
          </div>
        </form>

        <section className="rounded-3xl border border-line bg-card p-6 space-y-3">
          <div className="flex items-center gap-2">
            <Target className="h-4 w-4 text-accent" />
            <h2 className="text-base font-serif font-medium text-ink">Your Goals</h2>
          </div>
          {loading ? (
            <div data-testid="goals-skeleton" className="h-20 rounded-xl bg-soft animate-pulse" />
          ) : !overview || overview.goals.length === 0 ? (
            <p className="text-xs text-mute" data-testid="goals-empty">No goals added yet.</p>
          ) : (
            <div className="space-y-3">
              {overview.goals.map((g) => (
                <div key={g.id} className="rounded-2xl border border-line bg-bg p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-md bg-soft px-1.5 py-0.5 text-[10px] font-semibold text-ink">P{g.priority}</span>
                      <span className="font-semibold text-ink text-sm">{g.name}</span>
                      {g.is_funded && <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-300">Funded</span>}
                      {g.is_past_due && !g.is_funded && <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-semibold text-red-700 dark:text-red-300">Past due</span>}
                      {!g.feasible && <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300">Exceeds savings share</span>}
                    </div>
                    <div className="text-mute">
                      {formatINR(g.saved_paise / 100, { hideAmount: hideAmounts })} / {formatINR(g.target_amount_paise / 100, { hideAmount: hideAmounts })} ({g.progress_pct}%) · Target {formatISTDate(g.target_date)} · Suggested {formatINR(g.suggested_monthly_paise / 100, { hideAmount: hideAmounts })}/mo
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button type="button" onClick={() => handleReprioritize(g, -1)} aria-label={`Raise priority of ${g.name}`} className="rounded-lg border border-line p-1.5 text-mute hover:text-ink">
                      <ArrowUp className="h-3.5 w-3.5" />
                    </button>
                    <button type="button" onClick={() => handleReprioritize(g, 1)} aria-label={`Lower priority of ${g.name}`} className="rounded-lg border border-line p-1.5 text-mute hover:text-ink">
                      <ArrowDown className="h-3.5 w-3.5" />
                    </button>
                    <button type="button" onClick={() => handleDelete(g.id)} aria-label={`Delete ${g.name}`} className="rounded-lg border border-line p-1.5 text-mute hover:text-red-600">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
