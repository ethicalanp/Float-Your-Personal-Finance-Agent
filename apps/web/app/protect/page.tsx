"use client";

import { useState, useEffect } from "react";
import {
  ShieldAlert,
  AlertTriangle,
  PhoneCall,
  CheckCircle2,
  Clock,
  Search,
  PlusCircle,
  ExternalLink,
  LifeBuoy,
} from "lucide-react";
import AppShell from "@/components/AppShell";
import { getApiClient } from "@/lib/api";
import type {
  RecoveryCaseResponse,
  ScamCheckResponse,
  VerifiedContact,
} from "@float/api-client";

export default function ProtectPage() {
  const [activeTab, setActiveTab] = useState<"check" | "checklist" | "recovery" | "contacts">("check");

  // Scam Checker state
  const [messageText, setMessageText] = useState("");
  const [checking, setChecking] = useState(false);
  const [scamResult, setScamResult] = useState<ScamCheckResponse | null>(null);
  const [checkError, setCheckError] = useState<string | null>(null);

  // Recovery Cases state
  const [cases, setCases] = useState<RecoveryCaseResponse[]>([]);
  const [loadingCases, setLoadingCases] = useState(false);
  const [showNewCaseForm, setShowNewCaseForm] = useState(false);
  const [newScamType, setNewScamType] = useState("phishing");
  const [newAmount, setNewAmount] = useState("");
  const [newSummary, setNewSummary] = useState("");
  const [caseError, setCaseError] = useState<string | null>(null);
  const [submittingCase, setSubmittingCase] = useState(false);

  // Contacts state
  const [contacts, setContacts] = useState<VerifiedContact[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [loadingContacts, setLoadingContacts] = useState(false);

  const api = getApiClient();

  async function handleCheckScam(e: React.FormEvent) {
    e.preventDefault();
    if (!messageText.trim()) return;

    setChecking(true);
    setCheckError(null);
    try {
      const res = await api.protect.checkScam(messageText);
      setScamResult(res);
    } catch (err: any) {
      setCheckError(err.message || "Failed to analyze message");
    } finally {
      setChecking(false);
    }
  }

  async function loadRecoveryCases() {
    setLoadingCases(true);
    try {
      const res = await api.protect.getRecoveryCases();
      setCases(res);
    } catch {
      // fallback
    } finally {
      setLoadingCases(false);
    }
  }

  async function handleCreateCase(e: React.FormEvent) {
    e.preventDefault();
    setCaseError(null);
    setSubmittingCase(true);
    try {
      const created = await api.protect.createRecoveryCase({
        scam_type: newScamType,
        amount_lost: newAmount ? parseFloat(newAmount) : undefined,
        incident_summary: newSummary,
      });
      setCases([created, ...cases]);
      setShowNewCaseForm(false);
      setNewAmount("");
      setNewSummary("");
    } catch (err: any) {
      setCaseError(err.message || "Failed to report recovery case");
    } finally {
      setSubmittingCase(false);
    }
  }

  async function loadContacts(query: string = "") {
    setLoadingContacts(true);
    try {
      const res = query
        ? await api.protect.searchVerifiedContacts(query)
        : await api.protect.getVerifiedContacts();
      setContacts(res);
    } catch {
      // Fallback contacts if offline
      setContacts([
        {
          id: "1",
          institution_name: "National Cyber Crime Helpline",
          category: "regulator",
          official_phone: "1930",
          official_portal: "https://cybercrime.gov.in",
          helpline_type: "Emergency Financial Fraud Toll-Free",
          verified_at: "2026-01-01T00:00:00Z",
        },
        {
          id: "2",
          institution_name: "State Bank of India (SBI)",
          category: "bank",
          official_phone: "1800111109",
          official_portal: "https://sbi.co.in",
          helpline_type: "Card & UPI Blocking Hotline",
          verified_at: "2026-01-01T00:00:00Z",
        },
        {
          id: "3",
          institution_name: "Kerala Police Cyberdome",
          category: "police",
          official_phone: "0471-2722215",
          official_portal: "https://cyberdome.kerala.gov.in",
          helpline_type: "State Cyber Security Centre",
          verified_at: "2026-01-01T00:00:00Z",
        },
      ]);
    } finally {
      setLoadingContacts(false);
    }
  }

  useEffect(() => {
    if (activeTab === "recovery") loadRecoveryCases();
    if (activeTab === "contacts") loadContacts();
  }, [activeTab]);

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header with 1930 Emergency Banner */}
        <div>
          <span className="cnl-kicker text-xs font-semibold text-accent uppercase tracking-wider">
            Protect & Recover
          </span>
          <h1 className="text-3xl font-serif font-normal text-ink sm:text-4xl">
            Fraud Defense Center
          </h1>
          <p className="mt-1 text-xs text-mute">
            Detect suspicious communications, track recovery steps, and consult verified official contacts.
          </p>
        </div>

        {/* 1930 Emergency Fast Dial Callout */}
        <div className="flex flex-col gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 sm:flex-row sm:items-center sm:justify-between dark:border-red-950/60 dark:bg-red-950/20">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-red-600 text-white">
              <PhoneCall className="h-5 w-5" />
            </div>
            <div>
              <h4 className="text-sm font-semibold text-red-950 dark:text-red-200">
                Lost money in a cyber fraud in the last 2 hours?
              </h4>
              <p className="text-xs text-red-800 dark:text-red-300">
                Call the National Cybercrime Reporting Portal helpline immediately for the &quot;Golden Hour&quot; freeze.
              </p>
            </div>
          </div>
          <a
            href="tel:1930"
            className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-red-600 px-4 py-2 text-xs font-bold text-white shadow-sm hover:bg-red-700 transition-colors"
          >
            <span>Dial 1930</span>
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-line gap-2 overflow-x-auto">
          {[
            { id: "check", label: "Scam Checker" },
            { id: "checklist", label: "First-Hour Checklist" },
            { id: "recovery", label: "Recovery Cases" },
            { id: "contacts", label: "Verified Contacts" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`border-b-2 px-4 py-2.5 text-xs font-medium whitespace-nowrap transition-colors ${
                activeTab === tab.id
                  ? "border-accent text-accent font-semibold"
                  : "border-transparent text-mute hover:text-ink"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* TAB 1: Scam Checker */}
        {activeTab === "check" && (
          <div className="space-y-6">
            <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm">
              <h2 className="text-base font-serif font-medium text-ink">Analyze a Message</h2>
              <p className="text-xs text-mute mt-0.5">
                Paste the suspicious SMS, WhatsApp notice, or job alert you received in English, Malayalam, or Manglish.
              </p>

              <form onSubmit={handleCheckScam} className="mt-4 space-y-3">
                <textarea
                  rows={4}
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  placeholder="e.g. Electricity bill unpaid. Power will be disconnected tonight at 9:30 PM. Call officer at 9876543210 or click http://bit.ly/kseb-pay"
                  className="w-full rounded-2xl border border-line bg-soft/40 p-4 text-xs text-ink placeholder-faint focus:border-accent focus:bg-card focus:outline-none focus:ring-1 focus:ring-accent"
                />

                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap gap-1.5">
                    <span className="text-[11px] text-mute py-1">Try example:</span>
                    <button
                      type="button"
                      onClick={() =>
                        setMessageText(
                          "Dear customer, your electricity power will be disconnected tonight. Pay immediately via http://bit.ly/kseb-update"
                        )
                      }
                      className="rounded-lg border border-line bg-soft/60 px-2.5 py-1 text-[11px] text-mute hover:text-ink"
                    >
                      Power cut threat
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setMessageText(
                          "Earn 5000 INR daily liking YouTube videos. Click http://bit.ly/task-earn to claim reward immediately."
                        )
                      }
                      className="rounded-lg border border-line bg-soft/60 px-2.5 py-1 text-[11px] text-mute hover:text-ink"
                    >
                      Task scam
                    </button>
                  </div>

                  <button
                    type="submit"
                    disabled={checking || !messageText.trim()}
                    className="inline-flex items-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-xs font-semibold text-bg transition-all hover:opacity-90 disabled:opacity-50"
                  >
                    <span>{checking ? "Analyzing..." : "Analyze Message"}</span>
                  </button>
                </div>
              </form>

              {checkError && (
                <div className="mt-4 rounded-xl bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">
                  {checkError}
                </div>
              )}
            </div>

            {/* Analysis Result Display */}
            {scamResult && (
              <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-mute font-medium">Risk Assessment:</span>
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-bold uppercase ${
                        scamResult.analysis.risk_tier === "CRITICAL"
                          ? "bg-red-900 text-white"
                          : scamResult.analysis.risk_tier === "HIGH"
                          ? "bg-red-600 text-white"
                          : scamResult.analysis.risk_tier === "MEDIUM"
                          ? "bg-amber-500 text-white"
                          : "bg-emerald-600 text-white"
                      }`}
                    >
                      {scamResult.analysis.risk_tier} RISK
                    </span>
                  </div>
                  <span className="text-xs text-faint">Score: {scamResult.analysis.risk_score}/100</span>
                </div>

                {/* Reasons */}
                {scamResult.analysis.reasons.length > 0 && (
                  <div className="space-y-1.5">
                    <h4 className="text-xs font-semibold text-ink uppercase tracking-wider">Identified Red Flags:</h4>
                    <ul className="space-y-1 text-xs text-mute">
                      {scamResult.analysis.reasons.map((r, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 mt-0.5" />
                          <span>{r}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Recommendations */}
                {scamResult.analysis.recommendations.length > 0 && (
                  <div className="space-y-1.5 border-t border-line pt-3">
                    <h4 className="text-xs font-semibold text-ink uppercase tracking-wider">Recommended Actions:</h4>
                    <ul className="space-y-1 text-xs text-mute">
                      {scamResult.analysis.recommendations.map((rec, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 mt-0.5" />
                          <span>{rec}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: First-Hour Checklist (Static & Offline First) */}
        {activeTab === "checklist" && (
          <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-6">
            <div className="flex items-center gap-3">
              <Clock className="h-6 w-6 text-accent shrink-0" />
              <div>
                <h2 className="text-lg font-serif font-medium text-ink">
                  First-Hour Emergency Checklist (Golden Hour)
                </h2>
                <p className="text-xs text-mute">
                  Follow these steps immediately if you have transferred money or shared OTP with a fraudster.
                </p>
              </div>
            </div>

            <div className="space-y-4">
              {[
                {
                  step: 1,
                  priority: "CRITICAL",
                  title: "Call National Helpline 1930",
                  desc: "Within 2 hours of the fraudulent transaction, call 1930. The Citizen Financial Cyber Fraud Reporting System can flag and freeze funds across beneficiary accounts before withdrawal.",
                },
                {
                  step: 2,
                  priority: "CRITICAL",
                  title: "Freeze Banking & UPI Access",
                  desc: "Immediately open your bank app or call your bank helpline to lock your debit card, credit card, and deregister UPI handle to prevent subsequent debits.",
                },
                {
                  step: 3,
                  priority: "HIGH",
                  title: "Preserve Evidence & UTR Numbers",
                  desc: "Save transaction SMS, UTR (Unique Transaction Reference) number, sender phone numbers, UPI IDs, and take screenshots of fake portals or WhatsApp chats.",
                },
                {
                  step: 4,
                  priority: "HIGH",
                  title: "File Formal Complaint on cybercrime.gov.in",
                  desc: "Submit a comprehensive incident complaint on the official Ministry of Home Affairs portal to generate a police acknowledgement number for your bank.",
                },
                {
                  step: 5,
                  priority: "MEDIUM",
                  title: "Submit Written Notice to Home Branch",
                  desc: "Per RBI Zero Liability circular, report unauthorized electronic transactions in writing to your home branch within 3 days for maximum zero-liability protection.",
                },
              ].map((item) => (
                <div key={item.step} className="rounded-2xl border border-line bg-soft/30 p-4 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-ink">Step {item.step}: {item.title}</span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${item.priority === "CRITICAL" ? "bg-red-600 text-white" : item.priority === "HIGH" ? "bg-amber-600 text-white" : "bg-soft text-mute"}`}>
                      {item.priority}
                    </span>
                  </div>
                  <p className="text-xs text-mute leading-relaxed">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 3: Recovery Cases */}
        {activeTab === "recovery" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-serif font-medium text-ink">Your Reported Incidents</h2>
                <p className="text-xs text-mute">Track progress and required steps for reported fraud events.</p>
              </div>
              <button
                onClick={() => setShowNewCaseForm(!showNewCaseForm)}
                className="inline-flex items-center gap-1.5 rounded-xl bg-ink px-3.5 py-2 text-xs font-semibold text-bg hover:opacity-90 transition-all"
              >
                <PlusCircle className="h-3.5 w-3.5" />
                <span>Report Incident</span>
              </button>
            </div>

            {/* New Case Form */}
            {showNewCaseForm && (
              <form onSubmit={handleCreateCase} className="rounded-2xl border border-line bg-card p-5 space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-ink">Log Incident Details</h3>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label className="text-[11px] font-semibold text-mute uppercase">Scam Type</label>
                    <select
                      value={newScamType}
                      onChange={(e) => setNewScamType(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-line bg-soft px-3 py-2 text-xs text-ink"
                    >
                      <option value="phishing">Phishing / Fake Link</option>
                      <option value="task_scam">Task / Part-Time Job Scam</option>
                      <option value="electricity_bill">Electricity / Utility Threat</option>
                      <option value="digital_arrest">Digital Arrest Threat</option>
                      <option value="fake_loan">Illegal Loan App</option>
                      <option value="unauthorized_upi">Unauthorized UPI Debit</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-[11px] font-semibold text-mute uppercase">Amount Lost (INR)</label>
                    <input
                      type="number"
                      value={newAmount}
                      onChange={(e) => setNewAmount(e.target.value)}
                      placeholder="e.g. 25000"
                      className="mt-1 w-full rounded-lg border border-line bg-soft px-3 py-2 text-xs text-ink"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-[11px] font-semibold text-mute uppercase">Incident Summary</label>
                  <textarea
                    rows={2}
                    required
                    value={newSummary}
                    onChange={(e) => setNewSummary(e.target.value)}
                    placeholder="Brief description of what happened..."
                    className="mt-1 w-full rounded-lg border border-line bg-soft px-3 py-2 text-xs text-ink"
                  />
                </div>

                {caseError && <p className="text-xs text-red-600">{caseError}</p>}

                <div className="flex justify-end gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => setShowNewCaseForm(false)}
                    className="rounded-lg border border-line px-3 py-1.5 text-xs text-mute hover:text-ink"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submittingCase}
                    className="rounded-lg bg-accent px-4 py-1.5 text-xs font-semibold text-white hover:bg-accent/90"
                  >
                    {submittingCase ? "Saving..." : "Save Case"}
                  </button>
                </div>
              </form>
            )}

            {/* Cases List */}
            {loadingCases ? (
              <p className="text-xs text-mute py-8 text-center">Loading recovery cases...</p>
            ) : cases.length === 0 ? (
              <div className="rounded-2xl border border-line bg-card p-8 text-center">
                <LifeBuoy className="mx-auto h-8 w-8 text-mute/50 mb-2" />
                <p className="text-xs text-mute">No recovery cases reported yet.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {cases.map((c) => (
                  <div key={c.id} className="rounded-2xl border border-line bg-card p-5 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-ink capitalize">{c.scam_type.replace(/_/g, " ")}</span>
                        {c.amount_lost && (
                          <span className="text-xs text-mute">₹{c.amount_lost.toLocaleString("en-IN")} lost</span>
                        )}
                      </div>
                      <span className="rounded-full bg-soft px-2.5 py-0.5 text-[11px] font-medium capitalize text-mute">
                        {c.status.replace(/_/g, " ")}
                      </span>
                    </div>
                    <p className="text-xs text-mute">{c.incident_summary}</p>
                    <div className="text-[10px] text-faint">Reported on {new Date(c.created_at).toLocaleDateString()}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 4: Verified Contacts */}
        {activeTab === "contacts" && (
          <div className="space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-base font-serif font-medium text-ink">Verified Helplines</h2>
                <p className="text-xs text-mute">Official verified customer support and cyber cell numbers.</p>
              </div>
              <div className="relative">
                <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-mute" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    loadContacts(e.target.value);
                  }}
                  placeholder="Search bank or helpline..."
                  className="rounded-lg border border-line bg-soft pl-8 pr-3 py-1.5 text-xs text-ink placeholder-faint focus:outline-none"
                />
              </div>
            </div>

            {loadingContacts ? (
              <p className="text-xs text-mute py-8 text-center">Loading contacts...</p>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {contacts.map((contact) => (
                  <div key={contact.id} className="rounded-2xl border border-line bg-card p-4 space-y-1">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-bold text-ink">{contact.institution_name}</h4>
                      <span className="text-[10px] uppercase font-semibold text-accent">{contact.category}</span>
                    </div>
                    <p className="text-[11px] text-mute">{contact.helpline_type}</p>
                    <div className="pt-2 flex items-center justify-between">
                      <a
                        href={`tel:${contact.official_phone}`}
                        className="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-600 dark:text-emerald-400 hover:underline"
                      >
                        <PhoneCall className="h-3 w-3" />
                        <span>{contact.official_phone}</span>
                      </a>
                      {contact.official_portal && (
                        <a
                          href={contact.official_portal}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[11px] text-mute hover:text-ink inline-flex items-center gap-1"
                        >
                          <span>Portal</span>
                          <ExternalLink className="h-2.5 w-2.5" />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
