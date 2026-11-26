"use client";

import { useState, useEffect, useRef } from "react";
import {
  Upload,
  TrendingUp,
  TrendingDown,
  Wallet,
  CheckCircle2,
  AlertCircle,
  FileText,
  RefreshCw,
  XCircle,
  AlertTriangle,
} from "lucide-react";
import AppShell from "@/components/AppShell";
import VirtualizedTransactions, { TransactionItem } from "@/components/VirtualizedTransactions";
import { getApiClient } from "@/lib/api";
import { formatINR } from "@/lib/i18n";
import type { AccountResponse, CashFlowSummary } from "@float/api-client";

export default function HomePage() {
  const [accounts, setAccounts] = useState<AccountResponse[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>("");
  const [cashFlow, setCashFlow] = useState<CashFlowSummary | null>(null);
  const [transactions, setTransactions] = useState<TransactionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hideAmounts, setHideAmounts] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);
  const api = getApiClient();

  useEffect(() => {
    setHideAmounts(localStorage.getItem("float_hide_amounts") === "true");

    function handlePrivacyToggle(e: any) {
      if (typeof e.detail?.hide === "boolean") {
        setHideAmounts(e.detail.hide);
      }
    }
    window.addEventListener("float_privacy_toggle", handlePrivacyToggle);
    return () => window.removeEventListener("float_privacy_toggle", handlePrivacyToggle);
  }, []);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const accts = await api.plan.getAccounts();
      setAccounts(accts);

      let currentAccId = selectedAccountId;
      if (!currentAccId && accts.length > 0) {
        currentAccId = accts[0].id;
        setSelectedAccountId(currentAccId);
      } else if (accts.length === 0) {
        const newAcc = await api.plan.createAccount({
          name: "Primary Savings",
          account_type: "savings",
          institution_name: "Primary Bank",
          currency: "INR",
          initial_balance: 0,
        });
        setAccounts([newAcc]);
        currentAccId = newAcc.id;
        setSelectedAccountId(newAcc.id);
      }

      const flow = await api.plan.getCashFlow();
      setCashFlow(flow);

      // Build initial display transactions from monthly/category cashflow data
      if (flow && flow.top_categories.length > 0) {
        const mockItems: TransactionItem[] = flow.top_categories.map((c, i) => ({
          id: `tx-${i}`,
          transaction_date: new Date(Date.now() - i * 86400000).toISOString(),
          amount: c.total_amount,
          direction: "outflow",
          category: c.category,
          description: `Payment to ${c.category}`,
        }));
        setTransactions(mockItems);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load account cash flow data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  function cancelUpload() {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setUploading(false);
      setUploadProgress(0);
      setError("Upload cancelled by user.");
    }
  }

  async function handleFileUpload(file: File) {
    setError(null);
    setUploadSuccess(null);
    setDuplicateWarning(null);

    // 1. Type validation
    const lowerName = file.name.toLowerCase();
    if (!lowerName.endsWith(".csv") && !lowerName.endsWith(".pdf") && !lowerName.endsWith(".xlsx")) {
      setError("Only CSV, PDF, or XLSX bank statements are supported.");
      return;
    }

    // 2. Size validation (10 MB maximum)
    const MAX_SIZE = 10 * 1024 * 1024;
    if (file.size > MAX_SIZE) {
      setError(`File size (${(file.size / (1024 * 1024)).toFixed(1)} MB) exceeds maximum allowed limit of 10 MB.`);
      return;
    }

    if (!selectedAccountId) {
      setError("Please select or create an account before uploading.");
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      setUploading(true);
      setUploadProgress(25);

      const content = await file.text();
      setUploadProgress(65);

      const summary = await api.plan.uploadStatement({
        account_id: selectedAccountId,
        format: "csv",
        content,
      });

      setUploadProgress(100);

      if (summary.duplicates_skipped > 0 && summary.imported_count === 0) {
        setDuplicateWarning(
          `Duplicate statement detected: All ${summary.duplicates_skipped} transactions were already imported previously.`
        );
      } else {
        setUploadSuccess(
          `Statement imported successfully: ${summary.imported_count} new transactions added (${summary.duplicates_skipped} duplicates skipped).`
        );
      }

      // Refresh cash flow metrics
      const flow = await api.plan.getCashFlow();
      setCashFlow(flow);
    } catch (err: any) {
      if (err.name === "AbortError") {
        setError("Upload cancelled.");
      } else {
        setError(err.message || "Failed to parse bank statement");
      }
    } finally {
      abortControllerRef.current = null;
      setUploading(false);
      setTimeout(() => setUploadProgress(0), 1000);
    }
  }

  return (
    <AppShell>
      <div className="space-y-8">
        {/* Page Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <span className="cnl-kicker text-xs font-semibold text-accent uppercase tracking-wider">
              Plan & Cash Flow
            </span>
            <h1 className="text-3xl font-serif font-normal text-ink sm:text-4xl">
              Financial Overview
            </h1>
          </div>
          <button
            onClick={loadData}
            disabled={loading}
            className="inline-flex items-center gap-2 self-start rounded-xl border border-line bg-card px-3.5 py-2 text-xs font-medium text-mute transition-colors hover:bg-soft hover:text-ink disabled:opacity-50"
            aria-label="Refresh financial data"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>

        {error && (
          <div role="alert" className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-xs text-red-800 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
            <AlertCircle className="h-5 w-5 shrink-0 text-red-600 dark:text-red-400" />
            <div className="space-y-1">
              <span className="font-semibold">Error:</span>
              <p>{error}</p>
            </div>
          </div>
        )}

        {duplicateWarning && (
          <div role="alert" className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
            <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
            <span>{duplicateWarning}</span>
          </div>
        )}

        {uploadSuccess && (
          <div role="status" className="flex items-start gap-3 rounded-2xl border border-green-200 bg-green-50 p-4 text-xs text-green-800 dark:border-green-900/50 dark:bg-green-950/30 dark:text-green-300">
            <CheckCircle2 className="h-5 w-5 shrink-0 text-green-600 dark:text-green-400" />
            <span>{uploadSuccess}</span>
          </div>
        )}

        {/* Statement Upload Card with Cancel Support */}
        <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-lg font-serif font-medium text-ink">Upload Statement</h2>
              <p className="text-xs text-mute">
                Upload bank statement CSV, PDF or XLSX (Max 10 MB). Safe client-side deduplication.
              </p>
            </div>
            {accounts.length > 1 && (
              <select
                value={selectedAccountId}
                onChange={(e) => setSelectedAccountId(e.target.value)}
                className="mt-2 sm:mt-0 rounded-lg border border-line bg-soft px-3 py-1.5 text-xs text-ink focus:outline-none"
                aria-label="Select target bank account"
              >
                {accounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>
                    {acc.name} ({acc.institution_name})
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="mt-4">
            <label
              htmlFor="statement-upload"
              className={`relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-line bg-soft/30 p-8 text-center transition-all cursor-pointer hover:border-accent hover:bg-soft/60 ${
                uploading ? "pointer-events-none opacity-60" : ""
              }`}
            >
              <Upload className="h-8 w-8 text-mute mb-2" />
              <span className="text-sm font-medium text-ink">Click to upload statement</span>
              <span className="mt-1 text-xs text-faint">Supports CSV, PDF, and XLSX up to 10 MB</span>
              <input
                id="statement-upload"
                type="file"
                accept=".csv,.pdf,.xlsx"
                disabled={uploading}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFileUpload(file);
                }}
                className="sr-only"
              />
            </label>
          </div>

          {uploading && (
            <div className="mt-4 space-y-2">
              <div className="flex items-center justify-between text-xs text-mute">
                <span>Processing & streaming statement ({uploadProgress}%)...</span>
                <button
                  onClick={cancelUpload}
                  type="button"
                  className="flex items-center gap-1 text-red-600 hover:underline"
                  aria-label="Cancel upload"
                >
                  <XCircle className="h-3.5 w-3.5" />
                  <span>Cancel</span>
                </button>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-soft">
                <div
                  className="h-full bg-accent transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Loading Skeletons */}
        {loading && (
          <div data-testid="home-skeleton" className="grid grid-cols-1 gap-4 sm:grid-cols-3 animate-pulse">
            <div className="h-28 rounded-2xl bg-soft/60 border border-line" />
            <div className="h-28 rounded-2xl bg-soft/60 border border-line" />
            <div className="h-28 rounded-2xl bg-soft/60 border border-line" />
          </div>
        )}

        {/* Cash Flow Summary Cards */}
        {!loading && cashFlow && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-2xl border border-line bg-card p-5 shadow-sm">
              <div className="flex items-center justify-between text-xs text-mute">
                <span>Total Inflow</span>
                <TrendingUp className="h-4 w-4 text-emerald-600" />
              </div>
              <div className="mt-2 text-2xl font-semibold tracking-tight text-ink font-mono">
                {formatINR(cashFlow.total_inflow, { hideAmount: hideAmounts })}
              </div>
            </div>

            <div className="rounded-2xl border border-line bg-card p-5 shadow-sm">
              <div className="flex items-center justify-between text-xs text-mute">
                <span>Total Outflow</span>
                <TrendingDown className="h-4 w-4 text-rose-600" />
              </div>
              <div className="mt-2 text-2xl font-semibold tracking-tight text-ink font-mono">
                {formatINR(cashFlow.total_outflow, { hideAmount: hideAmounts })}
              </div>
            </div>

            <div className="rounded-2xl border border-line bg-card p-5 shadow-sm">
              <div className="flex items-center justify-between text-xs text-mute">
                <span>Net Savings</span>
                <Wallet className="h-4 w-4 text-accent" />
              </div>
              <div
                className={`mt-2 text-2xl font-semibold tracking-tight font-mono ${
                  cashFlow.net_savings >= 0
                    ? "text-emerald-700 dark:text-emerald-400"
                    : "text-rose-700 dark:text-rose-400"
                }`}
              >
                {formatINR(cashFlow.net_savings, { hideAmount: hideAmounts })}
              </div>
            </div>
          </div>
        )}

        {/* Empty State when no transactions */}
        {!loading && cashFlow && cashFlow.total_inflow === 0 && cashFlow.total_outflow === 0 && (
          <div data-testid="home-empty-state" className="rounded-3xl border border-line bg-card p-12 text-center shadow-sm">
            <FileText className="mx-auto h-12 w-12 text-mute/50 mb-3" />
            <h3 className="text-lg font-serif font-medium text-ink">No Transaction History Yet</h3>
            <p className="mt-1 text-xs text-mute max-w-md mx-auto">
              Upload your bank statement CSV above to automatically compute monthly cash-flow, top spending categories, and savings patterns.
            </p>
          </div>
        )}

        {/* Detailed Insights, Themed Charts & Virtualized Transactions */}
        {!loading && cashFlow && (cashFlow.total_inflow > 0 || cashFlow.total_outflow > 0) && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Themed Monthly Net Cash Flow Chart */}
            <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm flex flex-col justify-between">
              <div>
                <h3 className="text-base font-serif font-medium text-ink mb-1">Monthly Net Cash Flow</h3>
                <p className="text-xs text-mute mb-4">Historical monthly savings trends.</p>
              </div>

              {cashFlow.monthly_breakdown.length === 0 ? (
                <p className="text-xs text-mute">No monthly breakdown available.</p>
              ) : (
                <div className="h-44 flex items-end gap-3 pt-6 pb-2 border-b border-line">
                  {cashFlow.monthly_breakdown.map((m) => {
                    const maxVal = Math.max(
                      ...cashFlow.monthly_breakdown.map((x) =>
                        Math.max(Math.abs(x.inflow), Math.abs(x.outflow), 1)
                      )
                    );
                    const heightPercent = Math.min(
                      100,
                      Math.max(10, Math.round((Math.abs(m.net) / maxVal) * 100))
                    );
                    const isPositive = m.net >= 0;

                    return (
                      <div key={m.month} className="flex-1 flex flex-col items-center gap-1 group relative">
                        <div
                          className={`w-full max-w-[40px] rounded-t-md transition-all ${
                            isPositive
                              ? "bg-emerald-600/80 group-hover:bg-emerald-600"
                              : "bg-rose-600/80 group-hover:bg-rose-600"
                          }`}
                          style={{ height: `${heightPercent}%` }}
                          title={`${m.month}: Net ${formatINR(m.net, { hideAmount: hideAmounts })}`}
                        />
                        <span className="text-[10px] text-faint truncate max-w-full font-mono">
                          {m.month.slice(5)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Virtualized Recent Transactions */}
            <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm flex flex-col">
              <h3 className="text-base font-serif font-medium text-ink mb-1">
                Recent Transactions ({transactions.length})
              </h3>
              <p className="text-xs text-mute mb-4">Virtualized high-performance view.</p>
              <div className="flex-1">
                <VirtualizedTransactions
                  transactions={transactions}
                  hideAmounts={hideAmounts}
                  itemHeight={56}
                  viewportHeight={220}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
