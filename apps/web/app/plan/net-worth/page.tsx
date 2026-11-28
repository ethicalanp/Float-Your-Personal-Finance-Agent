"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { AlertCircle, AlertTriangle, Camera, Landmark, Pencil, Plus, Trash2 } from "lucide-react";
import AppShell from "@/components/AppShell";
import PlanTabs from "@/components/PlanTabs";
import { getApiClient } from "@/lib/api";
import type { NetWorthItem, NetWorthOverviewResponse, NetWorthSnapshot } from "@float/api-client";
import { formatINR, formatISTDate } from "@/lib/i18n";

function NetWorthHistoryChart({
  snapshots,
  hideAmounts,
}: {
  snapshots: NetWorthSnapshot[];
  hideAmounts: boolean;
}) {
  if (snapshots.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-line p-6 text-center text-sm text-mute">
        Save your first dated snapshot to track net worth over time.
      </div>
    );
  }

  const width = 640;
  const height = 180;
  const padX = 24;
  const padY = 20;
  const values = snapshots.map((s) => s.net_worth_paise / 100);
  const minVal = Math.min(0, ...values);
  const maxVal = Math.max(0, ...values);
  const span = maxVal - minVal || 1;

  const points = values.map((v, idx) => {
    const x =
      snapshots.length === 1
        ? width / 2
        : padX + (idx / (snapshots.length - 1)) * (width - padX * 2);
    const y = padY + ((maxVal - v) / span) * (height - padY * 2);
    return { x, y, v, date: snapshots[idx].snapshot_date };
  });

  const zeroY = padY + ((maxVal - 0) / span) * (height - padY * 2);
  const polyline = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  return (
    <div className="space-y-2" data-testid="net-worth-chart">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-44 overflow-visible">
        <line
          x1={padX}
          y1={zeroY}
          x2={width - padX}
          y2={zeroY}
          stroke="currentColor"
          strokeDasharray="4 4"
          className="text-line"
        />
        {points.length > 1 && (
          <polyline
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            className="text-accent"
            points={polyline}
          />
        )}
        {points.map((p, i) => (
          <g key={`${p.date}-${i}`}>
            <circle cx={p.x} cy={p.y} r="4.5" className={p.v < 0 ? "fill-bad" : "fill-accent"} />
          </g>
        ))}
      </svg>
      <div className="flex flex-wrap justify-between gap-2 text-xs text-mute">
        <span>
          First: {formatISTDate(snapshots[0].snapshot_date)} (
          {formatINR(values[0], { hideAmount: hideAmounts, compact: true })})
        </span>
        <span>
          Latest: {formatISTDate(snapshots[snapshots.length - 1].snapshot_date)} (
          {formatINR(values[values.length - 1], { hideAmount: hideAmounts, compact: true })})
        </span>
      </div>
    </div>
  );
}

export default function PlanNetWorthPage() {
  const [hideAmounts, setHideAmounts] = useState(false);
  const [data, setData] = useState<NetWorthOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [conflictMsg, setConflictMsg] = useState<string | null>(null);

  // Add item form
  const [name, setName] = useState("");
  const [itemType, setItemType] = useState<"asset" | "liability">("asset");
  const [category, setCategory] = useState("savings");
  const [amountRupees, setAmountRupees] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Inline edit state (preserved on 409)
  const [editingItem, setEditingItem] = useState<NetWorthItem | null>(null);
  const [editAmount, setEditAmount] = useState("");

  const api = getApiClient();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.plan.getNetWorth();
      setData(res);
    } catch (err: any) {
      setError(err?.message || "Failed to load net worth.");
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

  async function handleAdd(e: FormEvent) {
    e.preventDefault();
    const num = Number(amountRupees);
    if (!name.trim() || Number.isNaN(num) || num < 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await api.plan.createNetWorthItem({
        name: name.trim(),
        item_type: itemType,
        category,
        amount_paise: Math.round(num * 100),
      });
      setData(updated);
      setName("");
      setAmountRupees("");
    } catch (err: any) {
      setError(err?.message || "Could not add item.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSaveEdit(item: NetWorthItem) {
    const num = Number(editAmount);
    if (Number.isNaN(num) || num < 0) return;
    setError(null);
    setConflictMsg(null);
    try {
      const updated = await api.plan.updateNetWorthItem(item.id, {
        amount_paise: Math.round(num * 100),
        expected_version: item.version,
      });
      setData(updated);
      setEditingItem(null);
    } catch (err: any) {
      if (err?.status === 409) {
        setConflictMsg("This item was changed elsewhere. Latest values reloaded; your draft amount was kept.");
        const fresh = await api.plan.getNetWorth();
        setData(fresh);
        const latest = fresh.items.find((i) => i.id === item.id) || null;
        setEditingItem(latest);
      } else {
        setError(err?.message || "Could not update item.");
      }
    }
  }

  async function handleDelete(itemId: string) {
    setError(null);
    try {
      const updated = await api.plan.deleteNetWorthItem(itemId);
      setData(updated);
    } catch (err: any) {
      setError(err?.message || "Could not delete item.");
    }
  }

  async function handleSnapshot() {
    setError(null);
    try {
      const updated = await api.plan.createNetWorthSnapshot();
      setData(updated);
    } catch (err: any) {
      setError(err?.message || "Could not save snapshot.");
    }
  }

  return (
    <AppShell>
      <div className="space-y-6 max-w-5xl mx-auto">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-ink tracking-tight">Net worth</h1>
            <p className="text-sm text-mute mt-1">
              Track manual assets and liabilities, save dated snapshots, and keep stale valuations up to date.
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

        {conflictMsg && (
          <div role="alert" className="flex items-center gap-2 rounded-xl border border-warn/40 bg-warn/10 px-4 py-3 text-sm text-warn">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>{conflictMsg}</span>
          </div>
        )}

        {data && data.stale_count > 0 && (
          <div
            data-testid="stale-banner"
            className="flex items-center gap-2 rounded-xl border border-warn/40 bg-warn/10 px-4 py-3 text-sm text-warn"
          >
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>
              {data.stale_count} item(s) have not been updated in over 30 days. Review and refresh their values below.
            </span>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="rounded-2xl border border-line bg-card p-4">
            <p className="text-xs font-medium text-mute">Net worth</p>
            <p
              data-testid="net-worth-total"
              className={`text-2xl font-bold mt-1 ${data?.is_negative ? "text-bad" : "text-ink"}`}
            >
              {loading
                ? "—"
                : formatINR((data?.net_worth_paise ?? 0) / 100, {
                    hideAmount: hideAmounts,
                    compact: true,
                  })}
            </p>
          </div>
          <div className="rounded-2xl border border-line bg-card p-4">
            <p className="text-xs font-medium text-mute">Total assets</p>
            <p className="text-2xl font-bold text-ok mt-1" data-testid="total-assets">
              {loading
                ? "—"
                : formatINR((data?.total_assets_paise ?? 0) / 100, {
                    hideAmount: hideAmounts,
                    compact: true,
                  })}
            </p>
          </div>
          <div className="rounded-2xl border border-line bg-card p-4">
            <p className="text-xs font-medium text-mute">Total liabilities</p>
            <p className="text-2xl font-bold text-bad mt-1" data-testid="total-liabilities">
              {loading
                ? "—"
                : formatINR((data?.total_liabilities_paise ?? 0) / 100, {
                    hideAmount: hideAmounts,
                    compact: true,
                  })}
            </p>
          </div>
        </div>

        <section id="panel-net-worth" role="tabpanel" aria-labelledby="tab-net-worth" className="space-y-6">
          <div className="rounded-2xl border border-line bg-card p-5 space-y-4">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Landmark className="h-4 w-4 text-accent" />
                <h2 className="text-base font-semibold text-ink">History snapshots</h2>
              </div>
              <button
                type="button"
                onClick={handleSnapshot}
                data-testid="save-snapshot-btn"
                className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-3 py-2 text-xs font-semibold text-white hover:opacity-90"
              >
                <Camera className="h-3.5 w-3.5" />
                Save snapshot
              </button>
            </div>
            <NetWorthHistoryChart snapshots={data?.snapshots ?? []} hideAmounts={hideAmounts} />
          </div>

          <form onSubmit={handleAdd} className="rounded-2xl border border-line bg-card p-5 space-y-4">
            <h2 className="text-base font-semibold text-ink">Add asset or liability</h2>
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
              <input
                type="text"
                required
                placeholder="Name (e.g. PPF, Home Loan)"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
              />
              <select
                value={itemType}
                onChange={(e) => setItemType(e.target.value as "asset" | "liability")}
                className="rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
              >
                <option value="asset">Asset</option>
                <option value="liability">Liability</option>
              </select>
              <input
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="Category"
                className="rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
              />
              <input
                type="number"
                min="0"
                step="1"
                required
                placeholder="Amount (₹)"
                value={amountRupees}
                onChange={(e) => setAmountRupees(e.target.value)}
                className="rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
              />
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-white hover:opacity-90"
            >
              <Plus className="h-3.5 w-3.5" />
              Add item
            </button>
          </form>

          <div className="space-y-3">
            {(data?.items ?? []).map((item) => (
              <div
                key={item.id}
                data-testid={`nw-item-${item.id}`}
                className="rounded-2xl border border-line bg-card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-ink">{item.name}</span>
                    <span className="rounded-full bg-soft border border-line px-2 py-0.5 text-xs text-mute">
                      {item.item_type === "asset" ? "Asset" : "Liability"} · {item.category}
                    </span>
                    {item.is_stale && (
                      <span className="rounded-full bg-warn/15 border border-warn/40 px-2 py-0.5 text-xs font-medium text-warn">
                        Stale ({item.days_since_update}d)
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-mute mt-1">Updated {formatISTDate(item.valued_at)}</p>
                </div>

                <div className="flex items-center gap-2">
                  {editingItem?.id === item.id ? (
                    <>
                      <input
                        type="number"
                        min="0"
                        value={editAmount}
                        onChange={(e) => setEditAmount(e.target.value)}
                        className="w-28 rounded-lg border border-line bg-soft px-2 py-1 text-sm text-ink"
                      />
                      <button
                        type="button"
                        onClick={() => handleSaveEdit(editingItem)}
                        className="rounded-lg bg-accent px-2.5 py-1 text-xs font-semibold text-white"
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingItem(null)}
                        className="rounded-lg border border-line px-2.5 py-1 text-xs text-mute"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <span className="text-sm font-bold text-ink">
                        {formatINR(item.amount_paise / 100, { hideAmount: hideAmounts, compact: true })}
                      </span>
                      <button
                        type="button"
                        aria-label={`Edit ${item.name}`}
                        onClick={() => {
                          setEditingItem(item);
                          setEditAmount(String(Math.round(item.amount_paise / 100)));
                        }}
                        className="rounded-lg border border-line p-1.5 text-mute hover:text-ink"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Delete ${item.name}`}
                        onClick={() => handleDelete(item.id)}
                        className="rounded-lg border border-line p-1.5 text-mute hover:text-bad"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </AppShell>
  );
}
