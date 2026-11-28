"use client";

import { useEffect, useState, type FormEvent } from "react";
import { AlertCircle, Calculator, ExternalLink, Shield, TrendingUp } from "lucide-react";
import AppShell from "@/components/AppShell";
import PlanTabs from "@/components/PlanTabs";
import { getApiClient } from "@/lib/api";
import type {
  InsuranceGapResponse,
  SipProjectionResponse,
  TaxComparisonResponse,
} from "@float/api-client";
import { formatINR } from "@/lib/i18n";

export default function PlanCalculatorsPage() {
  const [hideAmounts, setHideAmounts] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 1. SIP state
  const [sipMode, setSipMode] = useState<"forward" | "reverse">("forward");
  const [monthlySip, setMonthlySip] = useState("10000");
  const [targetAmount, setTargetAmount] = useState("5000000");
  const [lumpsum, setLumpsum] = useState("0");
  const [years, setYears] = useState("10");
  const [returnPct, setReturnPct] = useState("10");
  const [stepUpType, setStepUpType] = useState<"none" | "percent" | "amount">("none");
  const [stepUpInterval, setStepUpInterval] = useState<1 | 2 | 3 | 6 | 12>(12);
  const [stepUpPercent, setStepUpPercent] = useState("5");
  const [stepUpAmount, setStepUpAmount] = useState("500");
  const [adjustInflation, setAdjustInflation] = useState(true);
  const [inflationPct, setInflationPct] = useState("6");
  const [sipValidationError, setSipValidationError] = useState<string | null>(null);
  const [sipRes, setSipRes] = useState<SipProjectionResponse | null>(null);

  // 2. Insurance gap state
  const [annualIncome, setAnnualIncome] = useState("1200000");
  const [dependants, setDependants] = useState("2");
  const [lifeCover, setLifeCover] = useState("5000000");
  const [healthCover, setHealthCover] = useState("500000");
  const [liabilities, setLiabilities] = useState("0");
  const [insRes, setInsRes] = useState<InsuranceGapResponse | null>(null);

  // 3. Tax comparison state
  const [grossIncome, setGrossIncome] = useState("1275000");
  const [isSalaried, setIsSalaried] = useState(true);
  const [ded80c, setDed80c] = useState("150000");
  const [ded80d, setDed80d] = useState("25000");
  const [taxRes, setTaxRes] = useState<TaxComparisonResponse | null>(null);

  const api = getApiClient();

  useEffect(() => {
    setHideAmounts(localStorage.getItem("float_hide_amounts") === "true");
    const onPrivacy = (e: any) => {
      if (typeof e.detail?.hide === "boolean") setHideAmounts(e.detail.hide);
    };
    window.addEventListener("float_privacy_toggle", onPrivacy);
    return () => window.removeEventListener("float_privacy_toggle", onPrivacy);
  }, []);

  async function runSip(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSipValidationError(null);

    const yrNum = Number(years);
    const retNum = Number(returnPct);
    const infNum = Number(inflationPct);
    const lumpNum = Number(lumpsum || "0");
    if (!years.trim() || Number.isNaN(yrNum) || !Number.isInteger(yrNum) || yrNum < 1 || yrNum > 50) {
      setSipValidationError("Horizon must be a whole number between 1 and 50 years.");
      return;
    }
    if (!returnPct.trim() || Number.isNaN(retNum) || retNum < 0 || retNum > 30) {
      setSipValidationError("Expected annual return must be between 0% and 30%.");
      return;
    }
    if (Number.isNaN(lumpNum) || lumpNum < 0) {
      setSipValidationError("Lumpsum amount cannot be negative.");
      return;
    }
    if (adjustInflation && (Number.isNaN(infNum) || infNum < 0 || infNum > 20)) {
      setSipValidationError("Inflation rate must be between 0% and 20%.");
      return;
    }
    if (sipMode === "forward") {
      const sipNum = Number(monthlySip);
      if (!monthlySip.trim() || Number.isNaN(sipNum) || sipNum < 0) {
        setSipValidationError("Monthly SIP must be 0 or a positive amount.");
        return;
      }
    } else {
      const tgtNum = Number(targetAmount);
      if (!targetAmount.trim() || Number.isNaN(tgtNum) || tgtNum <= 0) {
        setSipValidationError("Target maturity amount must be greater than ₹0.");
        return;
      }
    }
    if (stepUpType === "percent") {
      const sp = Number(stepUpPercent);
      if (Number.isNaN(sp) || sp < 0 || sp > 100) {
        setSipValidationError("Step-up percentage must be between 0% and 100%.");
        return;
      }
    }
    if (stepUpType === "amount") {
      const sa = Number(stepUpAmount);
      if (Number.isNaN(sa) || sa < 0) {
        setSipValidationError("Step-up fixed amount cannot be negative.");
        return;
      }
    }

    try {
      const res = await api.plan.calculateSip({
        mode: sipMode,
        monthly_sip_paise: sipMode === "forward" ? Math.round(Number(monthlySip) * 100) : 0,
        target_amount_paise: sipMode === "reverse" ? Math.round(Number(targetAmount) * 100) : undefined,
        lumpsum_paise: Math.round(lumpNum * 100),
        years: yrNum,
        expected_return_pct: retNum,
        step_up_type: stepUpType,
        step_up_interval_months: stepUpInterval,
        step_up_percent: stepUpType === "percent" ? Number(stepUpPercent || 0) : 0,
        step_up_amount_paise: stepUpType === "amount" ? Math.round(Number(stepUpAmount || 0) * 100) : 0,
        adjust_for_inflation: adjustInflation,
        inflation_pct: infNum || 0,
      });
      setSipRes(res);
    } catch (err: any) {
      setError(err?.message || "Failed to calculate SIP projection.");
    }
  }

  async function runInsurance(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await api.plan.calculateInsuranceGap({
        annual_income_paise: Math.round(Number(annualIncome || 0) * 100),
        dependants: Number(dependants || 0),
        existing_life_cover_paise: Math.round(Number(lifeCover || 0) * 100),
        existing_health_cover_paise: Math.round(Number(healthCover || 0) * 100),
        liabilities_paise: Math.round(Number(liabilities || 0) * 100),
      });
      setInsRes(res);
    } catch (err: any) {
      setError(err?.message || "Failed to calculate insurance gap.");
    }
  }

  async function runTax(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await api.plan.compareTaxRegimes({
        gross_income_paise: Math.round(Number(grossIncome || 0) * 100),
        is_salaried: isSalaried,
        deduction_80c_paise: Math.round(Number(ded80c || 0) * 100),
        deduction_80d_paise: Math.round(Number(ded80d || 0) * 100),
      });
      setTaxRes(res);
    } catch (err: any) {
      setError(err?.message || "Failed to compare tax regimes.");
    }
  }

  return (
    <AppShell>
      <div className="space-y-6 max-w-5xl mx-auto">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-ink tracking-tight">Educational calculators</h1>
            <p className="text-sm text-mute mt-1">
              Deterministic math for SIP projections, insurance gap heuristics, and tax regime comparison. Educational only — no advice or filing.
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

        <section id="panel-calculators" role="tabpanel" aria-labelledby="tab-calculators" className="space-y-6">
          {/* 1. SIP & Projection Calculator */}
          <form onSubmit={runSip} noValidate className="rounded-2xl border border-line bg-card p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-accent" />
                <h2 className="text-lg font-semibold text-ink">1. SIP & projection calculator</h2>
              </div>
              <div className="inline-flex rounded-xl border border-line bg-soft p-1 gap-1" role="group" aria-label="SIP calculator mode">
                <button
                  type="button"
                  data-testid="sip-mode-forward"
                  onClick={() => {
                    setSipMode("forward");
                    setSipValidationError(null);
                  }}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                    sipMode === "forward" ? "bg-card text-ink shadow-sm" : "text-mute hover:text-ink"
                  }`}
                >
                  Forward projection
                </button>
                <button
                  type="button"
                  data-testid="sip-mode-reverse"
                  onClick={() => {
                    setSipMode("reverse");
                    setSipValidationError(null);
                  }}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                    sipMode === "reverse" ? "bg-card text-ink shadow-sm" : "text-mute hover:text-ink"
                  }`}
                >
                  Target SIP (Reverse)
                </button>
              </div>
            </div>

            <p className="text-xs text-mute" data-testid="sip-convention">
              Convention: monthly compounding at annual/12, contributions at the start of each month, step-up applied at the start of each block. Educational & illustrative only — not a guarantee or advice; taxes and fees ignored.
            </p>

            {sipValidationError && (
              <div role="alert" data-testid="sip-validation-error" className="rounded-xl border border-bad/40 bg-bad/10 px-3 py-2 text-xs text-bad">
                {sipValidationError}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {sipMode === "forward" ? (
                <label className="text-xs text-mute space-y-1">
                  <span>Monthly SIP (₹)</span>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    data-testid="sip-monthly-input"
                    value={monthlySip}
                    onChange={(e) => setMonthlySip(e.target.value)}
                    className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                  />
                </label>
              ) : (
                <label className="text-xs text-mute space-y-1">
                  <span>Target maturity amount (₹)</span>
                  <input
                    type="number"
                    min="1"
                    step="0.01"
                    data-testid="sip-target-input"
                    value={targetAmount}
                    onChange={(e) => setTargetAmount(e.target.value)}
                    className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                  />
                </label>
              )}
              <label className="text-xs text-mute space-y-1">
                <span>Lumpsum (₹)</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  data-testid="sip-lumpsum-input"
                  value={lumpsum}
                  onChange={(e) => setLumpsum(e.target.value)}
                  className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                />
              </label>
              <label className="text-xs text-mute space-y-1">
                <span>Horizon (years, 1–50)</span>
                <input
                  type="number"
                  min="1"
                  max="50"
                  data-testid="sip-years-input"
                  value={years}
                  onChange={(e) => setYears(e.target.value)}
                  className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                />
              </label>
              <label className="text-xs text-mute space-y-1">
                <span>Illustrative return (% p.a., 0–30)</span>
                <input
                  type="number"
                  min="0"
                  max="30"
                  step="0.5"
                  data-testid="sip-return-input"
                  value={returnPct}
                  onChange={(e) => setReturnPct(e.target.value)}
                  className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                />
              </label>
              <label className="text-xs text-mute space-y-1">
                <span>Step-up type</span>
                <select
                  data-testid="sip-stepup-type"
                  value={stepUpType}
                  onChange={(e) => setStepUpType(e.target.value as "none" | "percent" | "amount")}
                  className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                >
                  <option value="none">No step-up (plain SIP)</option>
                  <option value="percent">Percentage step-up (%)</option>
                  <option value="amount">Fixed ₹ amount step-up</option>
                </select>
              </label>
              {stepUpType !== "none" && (
                <label className="text-xs text-mute space-y-1">
                  <span>Step-up every (months)</span>
                  <select
                    data-testid="sip-stepup-interval"
                    value={stepUpInterval}
                    onChange={(e) => setStepUpInterval(Number(e.target.value) as 1 | 2 | 3 | 6 | 12)}
                    className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                  >
                    <option value={1}>Every 1 month</option>
                    <option value={2}>Every 2 months</option>
                    <option value={3}>Every 3 months</option>
                    <option value={6}>Every 6 months</option>
                    <option value={12}>Every 12 months</option>
                  </select>
                </label>
              )}
              {stepUpType === "percent" && (
                <label className="text-xs text-mute space-y-1">
                  <span>Step-up by (%)</span>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    step="0.5"
                    data-testid="sip-stepup-percent"
                    value={stepUpPercent}
                    onChange={(e) => setStepUpPercent(e.target.value)}
                    className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                  />
                </label>
              )}
              {stepUpType === "amount" && (
                <label className="text-xs text-mute space-y-1">
                  <span>Step-up by (₹)</span>
                  <input
                    type="number"
                    min="0"
                    step="100"
                    data-testid="sip-stepup-amount"
                    value={stepUpAmount}
                    onChange={(e) => setStepUpAmount(e.target.value)}
                    className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                  />
                </label>
              )}
              <label className="text-xs text-mute space-y-1">
                <span>Inflation (% p.a.)</span>
                <input
                  type="number"
                  min="0"
                  max="20"
                  step="0.5"
                  disabled={!adjustInflation}
                  data-testid="sip-inflation-input"
                  value={inflationPct}
                  onChange={(e) => setInflationPct(e.target.value)}
                  className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink disabled:opacity-50"
                />
              </label>
              <label className="flex items-center gap-2 text-xs text-ink pt-5">
                <input
                  type="checkbox"
                  data-testid="sip-inflation-toggle"
                  checked={adjustInflation}
                  onChange={(e) => setAdjustInflation(e.target.checked)}
                />
                <span>Adjust for inflation (real value)</span>
              </label>
            </div>
            <button
              type="submit"
              data-testid="run-sip-btn"
              className="rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-white hover:opacity-90"
            >
              Calculate projection
            </button>

            {sipRes && (
              <div className="space-y-4 pt-3 border-t border-line" data-testid="sip-result">
                <p className="text-xs font-medium text-warn">{sipRes.disclaimer}</p>
                {sipRes.mode === "reverse" && sipRes.required_starting_sip_paise !== null && sipRes.required_starting_sip_paise !== undefined && (
                  <div className="rounded-xl border border-accent/40 bg-accent/10 p-3" data-testid="sip-required-starting">
                    <p className="text-xs text-mute">Required starting monthly SIP</p>
                    <p className="text-lg font-bold text-ink">
                      {formatINR(sipRes.required_starting_sip_paise / 100, { hideAmount: hideAmounts })}
                    </p>
                  </div>
                )}
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                  <div className="rounded-xl bg-soft p-3" data-testid="sip-total-invested">
                    <p className="text-xs text-mute">Total invested</p>
                    <p className="text-base font-bold text-ink">
                      {formatINR(sipRes.total_invested_paise / 100, { hideAmount: hideAmounts })}
                    </p>
                  </div>
                  <div className="rounded-xl bg-soft p-3" data-testid="sip-estimated-returns">
                    <p className="text-xs text-mute">Estimated returns</p>
                    <p className="text-base font-bold text-ok">
                      {formatINR(sipRes.estimated_returns_paise / 100, { hideAmount: hideAmounts })}
                    </p>
                  </div>
                  <div className="rounded-xl bg-soft p-3" data-testid="sip-maturity-nominal">
                    <p className="text-xs text-mute">Maturity value (nominal)</p>
                    <p className="text-base font-bold text-ink">
                      {formatINR(sipRes.projected_nominal_paise / 100, { hideAmount: hideAmounts })}
                    </p>
                  </div>
                  <div className="rounded-xl bg-soft p-3" data-testid="sip-maturity-real">
                    <p className="text-xs text-mute">
                      {sipRes.adjust_for_inflation ? "Real value (inflation-adj.)" : "Extra from step-up"}
                    </p>
                    <p className="text-base font-bold text-accent" data-testid="sip-extra-stepup">
                      {formatINR(
                        (sipRes.adjust_for_inflation ? sipRes.projected_real_paise : sipRes.extra_from_stepup_paise) / 100,
                        { hideAmount: hideAmounts },
                      )}
                    </p>
                  </div>
                </div>
                {sipRes.extra_from_stepup_paise > 0 && (
                  <div className="rounded-xl border border-ok/40 bg-ok/10 px-3 py-2 text-xs text-ink" data-testid="sip-stepup-delta">
                    Extra from step-up vs plain SIP:{" "}
                    <strong>{formatINR(sipRes.extra_from_stepup_paise / 100, { hideAmount: hideAmounts })}</strong>{" "}
                    (plain SIP maturity:{" "}
                    {formatINR(sipRes.plain_sip_nominal_paise / 100, { hideAmount: hideAmounts })})
                  </div>
                )}

                {/* Invested vs Value chart */}
                {sipRes.yearly_schedule && sipRes.yearly_schedule.length > 0 && (
                  <div className="space-y-2" data-testid="sip-chart">
                    <p className="text-xs font-semibold text-ink">Invested vs projected value by year</p>
                    <div className="space-y-1.5">
                      {(() => {
                        const maxVal = Math.max(...sipRes.yearly_schedule.map((r) => r.nominal_value_paise), 1);
                        return sipRes.yearly_schedule.map((row) => {
                          const invPct = Math.round((row.invested_paise / maxVal) * 100);
                          const valPct = Math.round((row.nominal_value_paise / maxVal) * 100);
                          return (
                            <div key={row.year} className="flex items-center gap-2 text-xs">
                              <span className="w-10 shrink-0 text-mute">Y{row.year}</span>
                              <div className="flex-1 h-3 rounded-full bg-soft overflow-hidden relative">
                                <div
                                  className="h-full bg-accent/50 rounded-full"
                                  style={{ width: `${valPct}%` }}
                                />
                                <div
                                  className="h-full bg-ink/70 rounded-full absolute top-0 left-0"
                                  style={{ width: `${invPct}%` }}
                                />
                              </div>
                              <span className="w-28 text-right font-mono text-ink shrink-0">
                                {formatINR(row.nominal_value_paise / 100, { hideAmount: hideAmounts, compact: true })}
                              </span>
                            </div>
                          );
                        });
                      })()}
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                  {sipRes.illustrative_scenarios.map((sc) => (
                    <div key={sc.label} className="rounded-xl border border-line p-2.5">
                      <p className="font-semibold text-ink">{sc.label}</p>
                      <p className="text-mute">
                        Nominal: {formatINR(sc.nominal_corpus_paise / 100, { hideAmount: hideAmounts, compact: true })}
                      </p>
                      <p className="text-mute">
                        Real: {formatINR(sc.real_corpus_paise / 100, { hideAmount: hideAmounts, compact: true })}
                      </p>
                    </div>
                  ))}
                </div>

                {/* Year-wise table */}
                {sipRes.yearly_schedule && sipRes.yearly_schedule.length > 0 && (
                  <div className="overflow-x-auto" data-testid="sip-yearly-table">
                    <table className="w-full text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-line text-mute text-left">
                          <th className="py-1.5 pr-3">Year</th>
                          <th className="py-1.5 pr-3">Monthly SIP</th>
                          <th className="py-1.5 pr-3">Total invested</th>
                          <th className="py-1.5 pr-3">Returns</th>
                          <th className="py-1.5">Nominal value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sipRes.yearly_schedule.map((row) => (
                          <tr key={row.year} className="border-b border-line/50 text-ink">
                            <td className="py-1.5 pr-3 font-mono">{row.year}</td>
                            <td className="py-1.5 pr-3 font-mono">
                              {formatINR(row.monthly_contribution_paise / 100, { hideAmount: hideAmounts })}
                            </td>
                            <td className="py-1.5 pr-3 font-mono">
                              {formatINR(row.invested_paise / 100, { hideAmount: hideAmounts })}
                            </td>
                            <td className="py-1.5 pr-3 font-mono text-ok">
                              {formatINR(row.returns_paise / 100, { hideAmount: hideAmounts })}
                            </td>
                            <td className="py-1.5 font-mono font-semibold">
                              {formatINR(row.nominal_value_paise / 100, { hideAmount: hideAmounts })}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <ul className="list-disc pl-5 text-xs text-mute space-y-0.5">
                  {sipRes.assumptions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
          </form>

          {/* 2. Insurance Gap Check */}
          <form onSubmit={runInsurance} className="rounded-2xl border border-line bg-card p-5 space-y-4">
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-accent" />
              <h2 className="text-lg font-semibold text-ink">2. Insurance gap check</h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
              <label className="text-xs text-mute space-y-1">
                <span>Annual income (₹)</span>
                <input
                  type="number"
                  min="0"
                  value={annualIncome}
                  onChange={(e) => setAnnualIncome(e.target.value)}
                  className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                />
              </label>
              <label className="text-xs text-mute space-y-1">
                <span>Dependants</span>
                <input
                  type="number"
                  min="0"
                  max="20"
                  value={dependants}
                  onChange={(e) => setDependants(e.target.value)}
                  className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                />
              </label>
              <label className="text-xs text-mute space-y-1">
                <span>Existing life cover (₹)</span>
                <input
                  type="number"
                  min="0"
                  value={lifeCover}
                  onChange={(e) => setLifeCover(e.target.value)}
                  className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                />
              </label>
              <label className="text-xs text-mute space-y-1">
                <span>Existing health cover (₹)</span>
                <input
                  type="number"
                  min="0"
                  value={healthCover}
                  onChange={(e) => setHealthCover(e.target.value)}
                  className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                />
              </label>
              <label className="text-xs text-mute space-y-1">
                <span>Liabilities (₹)</span>
                <input
                  type="number"
                  min="0"
                  value={liabilities}
                  onChange={(e) => setLiabilities(e.target.value)}
                  className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                />
              </label>
            </div>
            <button
              type="submit"
              data-testid="run-insurance-btn"
              className="rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-white hover:opacity-90"
            >
              Check coverage heuristic
            </button>

            {insRes && (
              <div className="space-y-3 pt-2 border-t border-line" data-testid="insurance-result">
                <p className="text-xs font-medium text-warn">{insRes.disclaimer}</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                  <div className="rounded-xl bg-soft p-3">
                    <p className="text-xs text-mute">Life cover heuristic vs gap</p>
                    <p className="font-bold text-ink">
                      Target: {formatINR(insRes.recommended_life_cover_paise / 100, { hideAmount: hideAmounts, compact: true })} · Gap:{" "}
                      {formatINR(insRes.life_cover_gap_paise / 100, { hideAmount: hideAmounts, compact: true })}
                    </p>
                  </div>
                  <div className="rounded-xl bg-soft p-3">
                    <p className="text-xs text-mute">Health cover heuristic vs gap</p>
                    <p className="font-bold text-ink">
                      Target: {formatINR(insRes.recommended_health_cover_paise / 100, { hideAmount: hideAmounts, compact: true })} · Gap:{" "}
                      {formatINR(insRes.health_cover_gap_paise / 100, { hideAmount: hideAmounts, compact: true })}
                    </p>
                  </div>
                </div>
                <ul className="list-disc pl-5 text-xs text-mute space-y-0.5">
                  {insRes.assumptions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
          </form>

          {/* 3. Tax Regime Comparison */}
          <form onSubmit={runTax} className="rounded-2xl border border-line bg-card p-5 space-y-4">
            <div className="flex items-center gap-2">
              <Calculator className="h-5 w-5 text-accent" />
              <h2 className="text-lg font-semibold text-ink">3. Tax regime comparison</h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
              <label className="text-xs text-mute space-y-1">
                <span>Gross annual income (₹)</span>
                <input
                  type="number"
                  min="0"
                  value={grossIncome}
                  onChange={(e) => setGrossIncome(e.target.value)}
                  className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                />
              </label>
              <label className="text-xs text-mute space-y-1">
                <span>80C deductions (₹, Old)</span>
                <input
                  type="number"
                  min="0"
                  max="150000"
                  value={ded80c}
                  onChange={(e) => setDed80c(e.target.value)}
                  className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                />
              </label>
              <label className="text-xs text-mute space-y-1">
                <span>80D health (₹, Old)</span>
                <input
                  type="number"
                  min="0"
                  max="100000"
                  value={ded80d}
                  onChange={(e) => setDed80d(e.target.value)}
                  className="w-full rounded-xl border border-line bg-soft px-3 py-2 text-sm text-ink"
                />
              </label>
              <label className="flex items-center gap-2 text-xs text-ink pt-5">
                <input
                  type="checkbox"
                  checked={isSalaried}
                  onChange={(e) => setIsSalaried(e.target.checked)}
                />
                <span>Salaried (standard deduction)</span>
              </label>
            </div>
            <button
              type="submit"
              data-testid="run-tax-btn"
              className="rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-white hover:opacity-90"
            >
              Compare regimes
            </button>

            {taxRes && (
              <div className="space-y-3 pt-2 border-t border-line" data-testid="tax-result">
                <p className="text-xs font-medium text-warn">{taxRes.educational_notice}</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                  <div className="rounded-xl bg-soft p-3">
                    <p className="text-xs text-mute">{taxRes.new_regime.regime}</p>
                    <p className="text-base font-bold text-ink">
                      Estimated tax: {formatINR(taxRes.new_regime.total_tax_paise / 100, { hideAmount: hideAmounts, compact: true })}
                    </p>
                    <p className="text-xs text-mute">
                      Taxable: {formatINR(taxRes.new_regime.taxable_income_paise / 100, { hideAmount: hideAmounts, compact: true })}
                    </p>
                  </div>
                  <div className="rounded-xl bg-soft p-3">
                    <p className="text-xs text-mute">{taxRes.old_regime.regime}</p>
                    <p className="text-base font-bold text-ink">
                      Estimated tax: {formatINR(taxRes.old_regime.total_tax_paise / 100, { hideAmount: hideAmounts, compact: true })}
                    </p>
                    <p className="text-xs text-mute">
                      Taxable: {formatINR(taxRes.old_regime.taxable_income_paise / 100, { hideAmount: hideAmounts, compact: true })}
                    </p>
                  </div>
                </div>
                <p className="text-xs text-mute flex flex-wrap items-center gap-2">
                  <span>
                    {taxRes.financial_year} (v{taxRes.version}, as of {taxRes.as_of})
                  </span>
                  <a
                    href={taxRes.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-accent underline"
                  >
                    Official source <ExternalLink className="h-3 w-3" />
                  </a>
                </p>
              </div>
            )}
          </form>
        </section>
      </div>
    </AppShell>
  );
}
