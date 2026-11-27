"use client";

import { useState, useEffect, useRef } from "react";
import {
  Repeat,
  Plus,
  Pause,
  Play,
  Trash2,
  Bell,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
} from "lucide-react";
import AppShell from "@/components/AppShell";
import { getApiClient } from "@/lib/api";
import type {
  BillRemindersResponse,
  RecurringCommitmentItem,
  RecurringSuggestionItem,
} from "@float/api-client";
import {
  formatINR,
  formatISTDate,
  getActiveLanguage,
  getTranslation,
  type Language,
} from "@/lib/i18n";

export default function RecurringPage() {
  const [lang, setLang] = useState<Language>("en");
  const [hideAmounts, setHideAmounts] = useState(false);

  const [commitments, setCommitments] = useState<RecurringCommitmentItem[]>([]);
  const [reminders, setReminders] = useState<BillRemindersResponse>({ due_soon: [], overdue: [] });
  const [suggestions, setSuggestions] = useState<RecurringSuggestionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // Add form state
  const [name, setName] = useState("");
  const [category, setCategory] = useState("Rent & Housing");
  const [expectedAmount, setExpectedAmount] = useState("");
  const [frequency, setFrequency] = useState<"weekly" | "monthly" | "quarterly" | "yearly">("monthly");
  const [dueDay, setDueDay] = useState("5");
  const [merchant, setMerchant] = useState("");
  const [submitting, setSubmitting] = useState(false);
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

  async function loadAll() {
    setLoading(true);
    setError(null);
    try {
      const [c, r, s] = await Promise.all([
        api.recurring.listCommitments(true),
        api.recurring.getReminders(),
        api.recurring.getSuggestions(),
      ]);
      setCommitments(c);
      setReminders(r);
      setSuggestions(s);
    } catch (err: any) {
      setError(err?.message || "Failed to load recurring payments.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleAddCommitment(e: React.FormEvent) {
    e.preventDefault();
    if (isSubmitting.current) return;
    const amt = Number(expectedAmount);
    if (!name.trim() || !amt || amt <= 0) {
      setError("Please enter a valid name and positive INR amount.");
      return;
    }

    isSubmitting.current = true;
    setSubmitting(true);
    setError(null);
    setStatusMsg(null);
    try {
      await api.recurring.createCommitment({
        name: name.trim(),
        category,
        expected_amount: amt,
        frequency,
        due_rule_day: Math.min(31, Math.max(1, Number(dueDay) || 1)),
        merchant: merchant.trim() || name.trim(),
        merchant_keywords: merchant.trim() ? [merchant.trim().toLowerCase()] : undefined,
      });
      setName("");
      setExpectedAmount("");
      setMerchant("");
      setStatusMsg("Recurring commitment added.");
      await loadAll();
    } catch (err: any) {
      setError(err?.message || "Could not add commitment.");
    } finally {
      setSubmitting(false);
      isSubmitting.current = false;
    }
  }

  async function handleTogglePause(c: RecurringCommitmentItem) {
    try {
      await api.recurring.updateCommitment(c.id, {
        is_active: !c.is_active,
        expected_version: c.version,
      });
      setStatusMsg(c.is_active ? `Paused ${c.name}.` : `Resumed ${c.name}.`);
      await loadAll();
    } catch (err: any) {
      if (err?.status === 409 || /conflict|concurrently/i.test(err?.message || "")) {
        await loadAll();
        setError("This recurring payment was changed elsewhere. Latest values reloaded.");
      } else {
        setError(err?.message || "Failed to update commitment.");
      }
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.recurring.deleteCommitment(id);
      setStatusMsg("Commitment removed.");
      await loadAll();
    } catch (err: any) {
      setError(err?.message || "Failed to remove commitment.");
    }
  }

  async function handleConfirmSuggestion(s: RecurringSuggestionItem) {
    try {
      await api.recurring.createCommitment({
        name: s.suggested_name,
        category: s.category,
        expected_amount: s.expected_amount,
        frequency: s.frequency,
        due_rule_day: s.due_rule_day,
        merchant: s.merchant,
        merchant_keywords: [s.merchant.toLowerCase()],
        origin: "suggested_confirmed",
      });
      setStatusMsg(`Confirmed ${s.suggested_name}.`);
      await loadAll();
    } catch (err: any) {
      setError(err?.message || "Failed to confirm candidate.");
    }
  }

  const t = getTranslation(lang).recurring;

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto space-y-6 pb-16">
        <div>
          <span className="cnl-kicker">Recurring</span>
          <h1 className="text-2xl sm:text-3xl font-serif font-normal text-ink mt-1">{t.title}</h1>
          <p className="text-xs sm:text-sm text-mute mt-1">{t.subtitle}</p>
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
          <div data-testid="recurring-skeleton" className="rounded-3xl border border-line bg-card p-6 animate-pulse space-y-3">
            <div className="h-5 w-40 rounded bg-soft" />
            <div className="h-16 w-full rounded bg-soft" />
          </div>
        ) : (
          <>
            {/* Due Soon & Overdue Strip */}
            <section data-testid="due-soon-strip" className="rounded-3xl border border-line bg-card p-5 space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                <Bell className="h-4 w-4 text-accent" />
                <span>{t.dueSoon}</span>
              </div>
              {reminders.due_soon.length === 0 && reminders.overdue.length === 0 ? (
                <p className="text-xs text-mute">No bills due in the next 7 days.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {[...reminders.overdue, ...reminders.due_soon].map((r) => (
                    <div
                      key={r.occurrence_id}
                      className={`rounded-xl border px-3 py-2 text-xs ${
                        r.status === "overdue" || r.status === "missed"
                          ? "border-red-400/50 bg-red-500/10 text-ink"
                          : "border-line bg-soft/40 text-ink"
                      }`}
                    >
                      <div className="font-semibold flex items-center gap-1">
                        {(r.status === "overdue" || r.status === "missed") && (
                          <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
                        )}
                        <span>{r.name}</span>
                      </div>
                      <div className="text-[11px] text-mute">
                        {formatINR(r.expected_amount, { hideAmount: hideAmounts })} · {formatISTDate(r.due_date)} ({r.status})
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Add Commitment Form */}
            <form onSubmit={handleAddCommitment} className="rounded-3xl border border-line bg-card p-6 space-y-4">
              <div className="flex items-center gap-2">
                <Plus className="h-4 w-4 text-accent" />
                <h2 className="text-base font-serif font-medium text-ink">{t.addCommitment}</h2>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label htmlFor="rec-name" className="block text-xs font-medium text-ink mb-1">Name</label>
                  <input id="rec-name" type="text" required value={name} onChange={(e) => setName(e.target.value)} placeholder="House Rent / Netflix" className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink" />
                </div>
                <div>
                  <label htmlFor="rec-amount" className="block text-xs font-medium text-ink mb-1">Amount (INR)</label>
                  <input id="rec-amount" type="number" required min={1} value={expectedAmount} onChange={(e) => setExpectedAmount(e.target.value)} placeholder="15000" className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink" />
                </div>
                <div>
                  <label htmlFor="rec-category" className="block text-xs font-medium text-ink mb-1">Category</label>
                  <select id="rec-category" value={category} onChange={(e) => setCategory(e.target.value)} className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink">
                    <option value="Rent & Housing">Rent</option>
                    <option value="EMI">EMI</option>
                    <option value="SIP">SIP</option>
                    <option value="Insurance">Insurance</option>
                    <option value="Subscriptions">Subscription</option>
                    <option value="Utilities">Utilities</option>
                    <option value="Other">Other</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="rec-freq" className="block text-xs font-medium text-ink mb-1">Frequency</label>
                  <select id="rec-freq" value={frequency} onChange={(e) => setFrequency(e.target.value as any)} className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink">
                    <option value="monthly">Monthly</option>
                    <option value="weekly">Weekly</option>
                    <option value="quarterly">Quarterly</option>
                    <option value="yearly">Yearly</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="rec-day" className="block text-xs font-medium text-ink mb-1">Due Day (1–31)</label>
                  <input id="rec-day" type="number" min={1} max={31} value={dueDay} onChange={(e) => setDueDay(e.target.value)} className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink" />
                </div>
                <div>
                  <label htmlFor="rec-merchant" className="block text-xs font-medium text-ink mb-1">Merchant Keyword</label>
                  <input id="rec-merchant" type="text" value={merchant} onChange={(e) => setMerchant(e.target.value)} placeholder="netflix / landlord" className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink" />
                </div>
              </div>
              <div className="flex justify-end">
                <button type="submit" disabled={submitting} data-testid="add-recurring-btn" className="rounded-xl bg-ink px-4 py-2 text-xs font-semibold text-bg hover:opacity-90 disabled:opacity-50">
                  {submitting ? "Adding..." : t.addCommitment}
                </button>
              </div>
            </form>

            {/* Commitments List */}
            <section className="rounded-3xl border border-line bg-card p-6 space-y-3">
              <div className="flex items-center gap-2">
                <Repeat className="h-4 w-4 text-accent" />
                <h2 className="text-base font-serif font-medium text-ink">Your Recurring Commitments</h2>
              </div>
              {commitments.length === 0 ? (
                <p className="text-xs text-mute" data-testid="recurring-empty">No recurring commitments declared yet.</p>
              ) : (
                <div className="space-y-2">
                  {commitments.map((c) => (
                    <div key={c.id} className="flex items-center justify-between rounded-2xl border border-line bg-bg p-4 text-xs">
                      <div>
                        <div className="font-semibold text-ink flex items-center gap-2">
                          <span>{c.name}</span>
                          {!c.is_active && (
                            <span className="rounded-full bg-soft px-2 py-0.5 text-[10px] text-mute">PAUSED</span>
                          )}
                        </div>
                        <div className="text-[11px] text-mute">
                          {formatINR(c.expected_amount, { hideAmount: hideAmounts })} · {c.frequency} · Day {c.due_rule_day} · {c.category}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button type="button" onClick={() => handleTogglePause(c)} aria-label={c.is_active ? `Pause ${c.name}` : `Resume ${c.name}`} className="rounded-lg border border-line p-1.5 text-mute hover:text-ink">
                          {c.is_active ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                        </button>
                        <button type="button" onClick={() => handleDelete(c.id)} aria-label={`Delete ${c.name}`} className="rounded-lg border border-line p-1.5 text-mute hover:text-red-600">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Candidates Inbox */}
            <section data-testid="candidates-inbox" className="rounded-3xl border border-line bg-card p-6 space-y-3">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-accent" />
                <h2 className="text-base font-serif font-medium text-ink">{t.candidatesInbox}</h2>
              </div>
              {suggestions.length === 0 ? (
                <p className="text-xs text-mute">No unconfirmed recurring candidates found in your history.</p>
              ) : (
                <div className="space-y-2">
                  {suggestions.map((s) => (
                    <div key={`${s.merchant}-${s.due_rule_day}`} className="flex items-center justify-between rounded-2xl border border-line bg-bg p-3 text-xs">
                      <div>
                        <div className="font-semibold text-ink">{s.suggested_name}</div>
                        <div className="text-[11px] text-mute">
                          {formatINR(s.expected_amount, { hideAmount: hideAmounts })} · Day {s.due_rule_day} · {s.detected_occurrences_count}x detected
                        </div>
                      </div>
                      <button type="button" onClick={() => handleConfirmSuggestion(s)} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white">
                        Confirm &amp; Add
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}
