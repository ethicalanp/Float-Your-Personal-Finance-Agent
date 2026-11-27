"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  PieChart,
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  RotateCcw,
  ArrowRight,
  Info,
  Bell,
  Sparkles,
} from "lucide-react";
import AppShell from "@/components/AppShell";
import PlanTabs from "@/components/PlanTabs";
import { getApiClient } from "@/lib/api";
import type {
  BillRemindersResponse,
  BudgetPlanOverviewResponse,
  RecurringSuggestionItem,
} from "@float/api-client";
import {
  formatINR,
  formatISTDate,
  getActiveLanguage,
  getTranslation,
  type Language,
} from "@/lib/i18n";

export default function PlanPage() {
  const [lang, setLang] = useState<Language>("en");
  const [hideAmounts, setHideAmounts] = useState(false);
  const [overview, setOverview] = useState<BudgetPlanOverviewResponse | null>(null);
  const [reminders, setReminders] = useState<BillRemindersResponse>({ due_soon: [], overdue: [] });
  const [suggestions, setSuggestions] = useState<RecurringSuggestionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draftRestored, setDraftRestored] = useState(false);

  const BUDGET_DRAFT_KEY = "float_plan_budget_draft";

  // Form state (INR rupees for inputs, converted to paise on submit)
  const [month, setMonth] = useState<string>(() => new Date().toISOString().slice(0, 7));
  const [incomeInr, setIncomeInr] = useState<string>("60000");
  const [extraIncomeInr, setExtraIncomeInr] = useState<string>("0");
  const [incomeMode, setIncomeMode] = useState<"fixed" | "irregular_avg" | "irregular_conservative">("fixed");
  const [needsPct, setNeedsPct] = useState<number>(50);
  const [wantsPct, setWantsPct] = useState<number>(30);
  const [savingsPct, setSavingsPct] = useState<number>(20);

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const isSubmitting = useRef(false);

  const api = getApiClient();

  useEffect(() => {
    setLang(getActiveLanguage());
    setHideAmounts(localStorage.getItem("float_hide_amounts") === "true");
    const onPrivacy = (e: any) => {
      if (typeof e.detail?.hide === "boolean") setHideAmounts(e.detail.hide);
    };
    window.addEventListener("float_privacy_toggle", onPrivacy);
    return () => window.removeEventListener("float_privacy_toggle", onPrivacy);
  }, []);

  function saveBudgetDraft() {
    if (typeof window === "undefined") return;
    try {
      sessionStorage.setItem(
        BUDGET_DRAFT_KEY,
        JSON.stringify({ incomeInr, extraIncomeInr, incomeMode, needsPct, wantsPct, savingsPct })
      );
    } catch {
      // ignore storage quota errors
    }
  }

  async function loadBudget(targetMonth?: string, preserveUnsaved = false) {
    setLoading(true);
    setLoadError(null);
    try {
      const [data, remRes, sugRes] = await Promise.all([
        api.plan.getBudget(targetMonth),
        api.recurring.getReminders().catch(() => ({ due_soon: [], overdue: [] })),
        api.recurring.getSuggestions().catch(() => []),
      ]);
      setOverview(data);
      setReminders(remRes);
      setSuggestions(sugRes);
      setMonth(data.month);
      let restored = false;
      if (typeof window !== "undefined") {
        const rawDraft = sessionStorage.getItem(BUDGET_DRAFT_KEY);
        if (rawDraft) {
          try {
            const d = JSON.parse(rawDraft);
            if (typeof d.incomeInr === "string") setIncomeInr(d.incomeInr);
            if (typeof d.extraIncomeInr === "string") setExtraIncomeInr(d.extraIncomeInr);
            if (d.incomeMode) setIncomeMode(d.incomeMode);
            if (typeof d.needsPct === "number") setNeedsPct(d.needsPct);
            if (typeof d.wantsPct === "number") setWantsPct(d.wantsPct);
            if (typeof d.savingsPct === "number") setSavingsPct(d.savingsPct);
            restored = true;
            setDraftRestored(true);
          } catch {
            sessionStorage.removeItem(BUDGET_DRAFT_KEY);
          }
        }
      }

      if (!restored && data.plan && !preserveUnsaved) {
        setIncomeInr(String(data.plan.monthly_income_paise / 100));
        setExtraIncomeInr(String(data.plan.extra_income_paise / 100));
        setIncomeMode(data.plan.income_mode);
        setNeedsPct(data.plan.needs_pct);
        setWantsPct(data.plan.wants_pct);
        setSavingsPct(data.plan.savings_pct);
      }
    } catch (err: any) {
      setLoadError(err?.message || "Unable to load budget plan.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadBudget(month);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const totalPct = Number((needsPct + wantsPct + savingsPct).toFixed(2));
  const unallocatedPct = Number((100 - totalPct).toFixed(2));
  const totalIncomeInr = (Number(incomeInr) || 0) + (Number(extraIncomeInr) || 0);
  const needsInr = Math.round((totalIncomeInr * needsPct) / 100);
  const wantsInr = Math.round((totalIncomeInr * wantsPct) / 100);
  const savingsInr = Math.max(0, totalIncomeInr - needsInr - wantsInr);

  function applyPreset(n: number, w: number, s: number) {
    setNeedsPct(n);
    setWantsPct(w);
    setSavingsPct(s);
    setSaveError(null);
  }

  function handleAmountInput(bucket: "needs" | "wants" | "savings", rawAmt: string) {
    const amt = Math.max(0, Number(rawAmt) || 0);
    if (totalIncomeInr <= 0) return;
    const pct = Math.min(100, Number(((amt / totalIncomeInr) * 100).toFixed(2)));
    if (bucket === "needs") setNeedsPct(pct);
    else if (bucket === "wants") setWantsPct(pct);
    else setSavingsPct(pct);
  }

  async function handleSavePlan(e: React.FormEvent) {
    e.preventDefault();
    if (isSubmitting.current) return;
    if (Math.abs(unallocatedPct) > 0.01) {
      setSaveError(`Percentages must sum to 100% (currently ${totalPct}%).`);
      return;
    }
    const basePaise = Math.round((Number(incomeInr) || 0) * 100);
    const extraPaise = Math.round((Number(extraIncomeInr) || 0) * 100);
    if (basePaise <= 0) {
      setSaveError("Monthly take-home income must be greater than ₹0.");
      return;
    }

    isSubmitting.current = true;
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(null);

    try {
      await api.plan.upsertBudget({
        month,
        monthly_income_paise: basePaise,
        extra_income_paise: Math.max(0, extraPaise),
        income_mode: incomeMode,
        needs_pct: needsPct,
        wants_pct: wantsPct,
        savings_pct: savingsPct,
        expected_version: overview?.plan?.version ?? 0,
      });
      if (typeof window !== "undefined") {
        sessionStorage.removeItem(BUDGET_DRAFT_KEY);
      }
      setDraftRestored(false);
      await loadBudget(month);
      setSaveSuccess("Budget plan saved.");
    } catch (err: any) {
      if (err?.status === 409 || /conflict|another tab/i.test(err?.message || "")) {
        await loadBudget(month, true);
        setSaveError(
          "This budget plan was changed elsewhere. Latest version reloaded — your unsaved edits are still in the form."
        );
      } else {
        setSaveError(err?.message || "Failed to save budget plan.");
      }
    } finally {
      setSaving(false);
      isSubmitting.current = false;
    }
  }

  const t = getTranslation(lang).plan;

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto space-y-6 pb-16">
        <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-xs text-mute">
          <span className="font-medium text-ink">Plan</span>
          <span aria-hidden="true">/</span>
          <span>{t.budgetTab}</span>
        </nav>

        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <span className="cnl-kicker">Plan</span>
            <h1 className="text-2xl sm:text-3xl font-serif font-normal text-ink mt-1">{t.title}</h1>
            <p className="text-xs sm:text-sm text-mute mt-1">{t.subtitle}</p>
          </div>
          <PlanTabs
            tabsLabel={t.tabsLabel}
            budgetLabel={t.budgetTab}
            recurringLabel={t.recurringTab}
            onBeforeNavigate={saveBudgetDraft}
          />
        </div>

        <div role="tabpanel" id="panel-budget" aria-labelledby="tab-budget" className="space-y-6">
          <div className="flex items-center gap-2 rounded-xl border border-line bg-soft/40 px-4 py-2.5 text-xs text-mute">
            <Info className="h-4 w-4 text-accent shrink-0" />
            <span>{t.disclaimer}</span>
          </div>

          {draftRestored && (
            <div role="status" className="flex items-center justify-between gap-2 rounded-xl border border-line bg-soft/60 px-4 py-2 text-xs text-ink">
              <span>Unsaved budget edits restored.</span>
              <button
                type="button"
                onClick={() => {
                  sessionStorage.removeItem(BUDGET_DRAFT_KEY);
                  setDraftRestored(false);
                  loadBudget(month);
                }}
                className="font-semibold text-accent hover:underline"
              >
                Discard draft
              </button>
            </div>
          )}

          {/* Plan Overview: Due Soon Strip & Recurring Candidates Prompt */}
          {!loading && !loadError && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <section
                data-testid="plan-due-soon-strip"
                className="rounded-2xl border border-line bg-card p-4 flex items-start justify-between gap-3"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-xs font-semibold text-ink">
                    <Bell className="h-4 w-4 text-accent shrink-0" />
                    <span>{t.dueSoonTitle}</span>
                  </div>
                  {reminders.overdue.length === 0 && reminders.due_soon.length === 0 ? (
                    <p className="text-xs text-mute">{t.noDueSoon}</p>
                  ) : (
                    <p className="text-xs text-mute">
                      {reminders.overdue.length + reminders.due_soon.length} bill(s) upcoming — next:{" "}
                      <span className="font-medium text-ink">
                        {[...reminders.overdue, ...reminders.due_soon][0].name}
                      </span>{" "}
                      ({formatINR([...reminders.overdue, ...reminders.due_soon][0].expected_amount, { hideAmount: hideAmounts })})
                    </p>
                  )}
                </div>
                <Link
                  href="/plan/recurring"
                  onClick={saveBudgetDraft}
                  className="inline-flex items-center gap-1 shrink-0 text-xs font-semibold text-accent hover:underline"
                >
                  <span>{t.viewRecurring}</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </section>

              <section
                data-testid="plan-candidates-prompt"
                className="rounded-2xl border border-line bg-card p-4 flex items-start justify-between gap-3"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-xs font-semibold text-ink">
                    <Sparkles className="h-4 w-4 text-accent shrink-0" />
                    <span>{t.candidatesTitle}</span>
                  </div>
                  {suggestions.length === 0 ? (
                    <p className="text-xs text-mute">No unconfirmed recurring patterns detected yet.</p>
                  ) : (
                    <p className="text-xs text-mute">
                      {suggestions.length} detected ({suggestions[0].suggested_name} ·{" "}
                      {formatINR(suggestions[0].expected_amount, { hideAmount: hideAmounts })})
                    </p>
                  )}
                </div>
                <Link
                  href="/plan/recurring#candidates"
                  onClick={saveBudgetDraft}
                  className="inline-flex items-center gap-1 shrink-0 text-xs font-semibold text-accent hover:underline"
                >
                  <span>{t.reviewCandidates}</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </section>
            </div>
          )}

        {loading && (
          <div data-testid="plan-skeleton" className="rounded-3xl border border-line bg-card p-6 animate-pulse space-y-4">
            <div className="h-6 w-48 rounded bg-soft" />
            <div className="h-24 w-full rounded bg-soft" />
          </div>
        )}

        {loadError && !loading && (
          <div role="alert" className="rounded-2xl border border-red-300 bg-red-50 dark:bg-red-950/30 p-4 text-xs text-red-700 dark:text-red-300 flex items-center justify-between">
            <span>{loadError}</span>
            <button type="button" onClick={() => loadBudget(month)} className="underline font-semibold">
              Retry
            </button>
          </div>
        )}

        {!loading && !loadError && overview && (
          <form onSubmit={handleSavePlan} className="space-y-6">
            {saveError && (
              <div role="alert" className="flex items-center gap-2 rounded-xl border border-red-300 bg-red-50 dark:bg-red-950/30 p-3 text-xs text-red-700 dark:text-red-300">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{saveError}</span>
              </div>
            )}
            {saveSuccess && (
              <div role="status" className="flex items-center gap-2 rounded-xl border border-emerald-300 bg-emerald-50 dark:bg-emerald-950/30 p-3 text-xs text-emerald-800 dark:text-emerald-300">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                <span>{saveSuccess}</span>
              </div>
            )}

            {overview.actuals.warnings.length > 0 && (
              <div role="alert" data-testid="budget-warnings" className="rounded-2xl border border-amber-400/50 bg-amber-500/10 p-4 space-y-1">
                {overview.actuals.warnings.map((w, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs font-medium text-ink">
                    <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
                    <span>{w}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Income Entry */}
            <section className="rounded-3xl border border-line bg-card p-6 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-serif font-medium text-ink">Monthly Income ({month})</h2>
                {overview.plan && (
                  <span className="text-[11px] text-mute">
                    v{overview.plan.version} · Updated {formatISTDate(overview.plan.updated_at)}
                  </span>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label htmlFor="budget-income" className="block text-xs font-medium text-ink mb-1">
                    Monthly Take-Home (INR)
                  </label>
                  <input
                    id="budget-income"
                    type="number"
                    min={1}
                    max={100000000}
                    step="1"
                    value={incomeInr}
                    onChange={(e) => setIncomeInr(e.target.value)}
                    className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink"
                  />
                </div>
                <div>
                  <label htmlFor="budget-extra-income" className="block text-xs font-medium text-ink mb-1">
                    Extra Income (Optional INR)
                  </label>
                  <input
                    id="budget-extra-income"
                    type="number"
                    min={0}
                    max={100000000}
                    step="1"
                    value={extraIncomeInr}
                    onChange={(e) => setExtraIncomeInr(e.target.value)}
                    className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink"
                  />
                </div>
                <div>
                  <label htmlFor="budget-income-mode" className="block text-xs font-medium text-ink mb-1">
                    Income Mode
                  </label>
                  <select
                    id="budget-income-mode"
                    value={incomeMode}
                    onChange={(e) => {
                      const mode = e.target.value as any;
                      setIncomeMode(mode);
                      if (mode === "irregular_avg" && overview.irregular_avg_paise > 0) {
                        setIncomeInr(String(Math.round(overview.irregular_avg_paise / 100)));
                      }
                    }}
                    className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink"
                  >
                    <option value="fixed">Fixed Salary</option>
                    <option value="irregular_avg">Irregular (3-Month Avg)</option>
                    <option value="irregular_conservative">Irregular (Conservative)</option>
                  </select>
                </div>
              </div>
            </section>

            {/* Interactive Split Editor */}
            <section className="rounded-3xl border border-line bg-card p-6 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <PieChart className="h-5 w-5 text-accent" />
                  <h2 className="text-base font-serif font-medium text-ink">Split Editor</h2>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => applyPreset(50, 30, 20)} className="rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink hover:bg-soft">
                    50 / 30 / 20
                  </button>
                  <button type="button" onClick={() => applyPreset(60, 20, 20)} className="rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink hover:bg-soft">
                    60 / 20 / 20
                  </button>
                  <button type="button" onClick={() => applyPreset(50, 20, 30)} className="rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink hover:bg-soft">
                    50 / 20 / 30
                  </button>
                  <button
                    type="button"
                    onClick={() => applyPreset(50, 30, 20)}
                    className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-mute hover:text-ink"
                  >
                    <RotateCcw className="h-3 w-3" />
                    <span>{t.resetDefault}</span>
                  </button>
                </div>
              </div>

              {/* Stacked Split Bar */}
              <div className="h-4 w-full overflow-hidden rounded-full bg-soft flex" aria-label="Budget allocation bar">
                <div style={{ width: `${Math.min(100, needsPct)}%` }} className="bg-emerald-500 transition-all" title={`Needs ${needsPct}%`} />
                <div style={{ width: `${Math.min(100, wantsPct)}%` }} className="bg-amber-500 transition-all" title={`Wants ${wantsPct}%`} />
                <div style={{ width: `${Math.min(100, savingsPct)}%` }} className="bg-indigo-500 transition-all" title={`Savings ${savingsPct}%`} />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                  { key: "needs" as const, label: "Needs", pct: needsPct, setPct: setNeedsPct, inr: needsInr, color: "bg-emerald-500" },
                  { key: "wants" as const, label: "Wants", pct: wantsPct, setPct: setWantsPct, inr: wantsInr, color: "bg-amber-500" },
                  { key: "savings" as const, label: "Savings", pct: savingsPct, setPct: setSavingsPct, inr: savingsInr, color: "bg-indigo-500" },
                ].map((b) => (
                  <div key={b.key} className="rounded-2xl border border-line bg-bg p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink">
                        <span className={`h-2.5 w-2.5 rounded-full ${b.color}`} />
                        {b.label}
                      </span>
                      <span className="text-xs font-semibold text-ink">
                        {formatINR(b.inr, { hideAmount: hideAmounts })}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      step={1}
                      aria-label={`${b.label} percentage slider`}
                      value={b.pct}
                      onChange={(e) => b.setPct(Number(e.target.value))}
                      className="w-full accent-emerald-600"
                    />
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label htmlFor={`pct-${b.key}`} className="block text-[11px] text-mute mb-0.5">%</label>
                        <input
                          id={`pct-${b.key}`}
                          type="number"
                          min={0}
                          max={100}
                          step="0.5"
                          value={b.pct}
                          onChange={(e) => b.setPct(Math.max(0, Math.min(100, Number(e.target.value) || 0)))}
                          className="w-full rounded-lg border border-line bg-card px-2 py-1 text-xs text-ink"
                        />
                      </div>
                      <div>
                        <label htmlFor={`amt-${b.key}`} className="block text-[11px] text-mute mb-0.5">INR</label>
                        <input
                          id={`amt-${b.key}`}
                          type="number"
                          min={0}
                          value={b.inr}
                          onChange={(e) => handleAmountInput(b.key, e.target.value)}
                          className="w-full rounded-lg border border-line bg-card px-2 py-1 text-xs text-ink"
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-line">
                <div className="text-xs">
                  <span className="text-mute">Total Allocated: </span>
                  <span className={`font-semibold ${Math.abs(unallocatedPct) > 0.01 ? "text-red-600 dark:text-red-400" : "text-ink"}`}>
                    {totalPct}%
                  </span>
                  {Math.abs(unallocatedPct) > 0.01 && (
                    <span data-testid="unallocated-indicator" className="ml-2 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:text-amber-300">
                      {t.unallocated}: {unallocatedPct}%
                    </span>
                  )}
                </div>
                <button
                  type="submit"
                  disabled={saving || Math.abs(unallocatedPct) > 0.01}
                  data-testid="save-budget-btn"
                  className="rounded-xl bg-ink px-5 py-2.5 text-xs font-semibold text-bg hover:opacity-90 disabled:opacity-50"
                >
                  {saving ? "Saving..." : t.savePlan}
                </button>
              </div>
            </section>

            {/* Plan vs Actual Progress */}
            <section className="rounded-3xl border border-line bg-card p-6 space-y-4">
              <h2 className="text-base font-serif font-medium text-ink">Plan vs Actual ({month})</h2>
              {!overview.actuals.has_transactions ? (
                <p className="text-xs text-mute" data-testid="plan-no-transactions">
                  No imported transactions for {month}. Upload a bank statement on Home to compare actual spending.
                </p>
              ) : (
                <div className="space-y-3">
                  {[
                    { label: "Needs", planned: needsInr, actual: overview.actuals.actual_needs_paise / 100 },
                    { label: "Wants", planned: wantsInr, actual: overview.actuals.actual_wants_paise / 100 },
                    { label: "Savings", planned: savingsInr, actual: overview.actuals.actual_savings_paise / 100 },
                  ].map((row) => {
                    const ratio = row.planned > 0 ? Math.min(100, Math.round((row.actual / row.planned) * 100)) : 0;
                    return (
                      <div key={row.label} className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="font-medium text-ink">{row.label}</span>
                          <span className="text-mute">
                            {formatINR(row.actual, { hideAmount: hideAmounts })} / {formatINR(row.planned, { hideAmount: hideAmounts })}
                          </span>
                        </div>
                        <div className="h-2 w-full rounded-full bg-soft overflow-hidden">
                          <div style={{ width: `${ratio}%` }} className="h-full bg-accent transition-all" />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          </form>
        )}
        </div>
      </div>
    </AppShell>
  );
}
