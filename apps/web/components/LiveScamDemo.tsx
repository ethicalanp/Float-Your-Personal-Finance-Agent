"use client";

import * as React from "react";
import { landingContent } from "@/content/landing";
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Loader2,
  Sparkles,
  RefreshCw,
  PhoneCall,
  ExternalLink,
} from "lucide-react";

interface ScamResult {
  risk_tier?: string;
  risk_score?: number;
  reasons?: string[];
  indicators?: string[];
  advice?: string;
  analysis?: {
    risk_tier?: string;
    risk_score?: number;
    indicators?: string[];
    is_scam?: boolean;
    advice?: string;
  };
}

export function LiveScamDemo() {
  const { liveDemo } = landingContent;
  const [inputMessage, setInputMessage] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [result, setResult] = React.useState<ScamResult | null>(null);
  const [errorStatus, setErrorStatus] = React.useState<number | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const handleCheck = async (textToCheck?: string) => {
    const text = (textToCheck ?? inputMessage).trim();
    if (!text) return;

    setLoading(true);
    setResult(null);
    setErrorStatus(null);
    setErrorMessage(null);

    try {
      const response = await fetch("/api/v1/protect/check", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ message: text }),
      });

      if (response.status === 503) {
        setErrorStatus(503);
        setErrorMessage(liveDemo.serviceUnavailableText);
        setLoading(false);
        return;
      }

      if (!response.ok) {
        setErrorStatus(response.status);
        setErrorMessage(liveDemo.errorText);
        setLoading(false);
        return;
      }

      const data = await response.json();
      setResult(data);
    } catch {
      setErrorStatus(500);
      setErrorMessage(liveDemo.errorText);
    } finally {
      setLoading(false);
    }
  };

  const currentTier = (
    result?.risk_tier ||
    result?.analysis?.risk_tier ||
    "SAFE"
  ).toUpperCase();

  const currentScore =
    result?.risk_score ?? result?.analysis?.risk_score ?? 0;

  const currentReasons =
    result?.reasons ||
    result?.indicators ||
    result?.analysis?.indicators ||
    [];

  const tierStyles = {
    SAFE: {
      bg: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20",
      badge: "bg-emerald-500 text-white",
      icon: <ShieldCheck size={20} className="text-emerald-600" />,
      label: "Safe / Low Risk",
    },
    SUSPICIOUS: {
      bg: "bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20",
      badge: "bg-amber-500 text-white",
      icon: <AlertTriangle size={20} className="text-amber-600" />,
      label: "Suspicious Warning",
    },
    DANGEROUS: {
      bg: "bg-red-500/10 text-red-700 dark:text-red-300 border-red-500/20",
      badge: "bg-accent text-white",
      icon: <ShieldAlert size={20} className="text-accent" />,
      label: "Dangerous Threat Detected",
    },
  }[currentTier] || {
    bg: "bg-soft text-ink border-line",
    badge: "bg-ink text-bg",
    icon: <ShieldCheck size={20} />,
    label: currentTier,
  };

  return (
    <section id="live-check" className="py-20 md:py-32">
      <div className="mx-auto max-w-[1100px] px-5 md:px-8">

        {/* Section Header */}
        <div className="flex flex-col items-center text-center">
          <div className="cnl-kicker">{liveDemo.kicker}</div>
          <h2 className="cnl-serif mt-4 text-[34px] leading-tight text-ink sm:text-[46px] md:text-[54px]">
            {liveDemo.title}
          </h2>
          <p className="mt-4 max-w-[640px] text-[15.5px] leading-relaxed text-mute">
            {liveDemo.description}
          </p>
        </div>

        {/* Demo Box Surface */}
        <div className="relative mt-12 overflow-hidden rounded-2xl border border-line bg-card p-6 shadow-2xl transition-all md:p-8">

          {/* Subtle Top Loading Line during analysis */}
          {loading && (
            <div className="absolute top-0 left-0 right-0 h-[2.5px] bg-agent/20 overflow-hidden">
              <div className="h-full bg-agent w-1/3 animate-[cnl-marquee_1.4s_linear_infinite]" />
            </div>
          )}

          {/* Quick Pre-fill Samples */}
          <div className="flex flex-col gap-2 border-b border-line pb-6 sm:flex-row sm:items-center sm:justify-between">
            <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-faint">
              Or load sample threat pattern:
            </span>
            <div className="flex flex-wrap gap-2">
              {liveDemo.samplePrompts.map((prompt, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => {
                    setInputMessage(prompt.text);
                    handleCheck(prompt.text);
                  }}
                  className="rounded-full border border-line bg-soft/70 px-3 py-1 font-mono text-[11px] text-mute transition-all hover:scale-105 hover:border-agent hover:text-ink active:scale-95"
                >
                  {prompt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Input Textarea Area */}
          <div className="mt-6">
            <label htmlFor="scam-input" className="sr-only">
              Suspicious message text
            </label>
            <textarea
              id="scam-input"
              rows={4}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder={liveDemo.inputPlaceholder}
              className="w-full rounded-xl border border-line bg-soft/30 p-4 font-mono text-[13.5px] text-ink placeholder:text-faint/80 focus:border-agent focus:outline-none focus:ring-1 focus:ring-agent transition-all"
            />
          </div>

          {/* Action Row */}
          <div className="mt-4 flex flex-col items-center justify-between gap-4 sm:flex-row">
            <p className="font-mono text-[11px] text-faint">
              Anonymous live evaluation &middot; Zero storage
            </p>

            <div className="flex w-full items-center justify-end gap-3 sm:w-auto">
              {inputMessage && (
                <button
                  type="button"
                  onClick={() => {
                    setInputMessage("");
                    setResult(null);
                    setErrorStatus(null);
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-[12.5px] font-medium text-mute hover:text-ink transition-transform active:scale-95"
                >
                  <RefreshCw size={14} />
                  <span>Clear</span>
                </button>
              )}

              <button
                type="button"
                disabled={loading || !inputMessage.trim()}
                onClick={() => handleCheck()}
                className="cnl-pill is-lg w-full sm:w-auto disabled:opacity-50"
              >
                {loading ? (
                  <span className="inline-flex items-center gap-2">
                    <Loader2 size={16} className="animate-spin text-agent" />
                    <span>Analyzing...</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-2">
                    <Sparkles size={16} className="text-accent" />
                    <span className="cnl-roll" data-t={liveDemo.buttonText}>
                      <span>{liveDemo.buttonText}</span>
                    </span>
                  </span>
                )}
              </button>
            </div>
          </div>

          {/* 503 State Message */}
          {errorStatus === 503 && (
            <div
              role="alert"
              className="mt-6 rounded-xl border border-amber-500/20 bg-amber-500/10 p-5 text-amber-800 dark:text-amber-200 animate-fade-in"
            >
              <div className="flex items-start gap-3">
                <AlertTriangle size={20} className="mt-0.5 text-amber-600" />
                <div>
                  <h4 className="font-semibold text-[14px]">
                    Service Temporarily Busy (503)
                  </h4>
                  <p className="mt-1 text-[13px] leading-relaxed">
                    {errorMessage}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Generic Error State Message */}
          {errorStatus && errorStatus !== 503 && (
            <div
              role="alert"
              className="mt-6 rounded-xl border border-red-500/20 bg-red-500/10 p-5 text-red-800 dark:text-red-200 animate-fade-in"
            >
              <div className="flex items-start gap-3">
                <AlertTriangle size={20} className="mt-0.5 text-accent" />
                <div>
                  <h4 className="font-semibold text-[14px]">Connection Error</h4>
                  <p className="mt-1 text-[13px] leading-relaxed">
                    {errorMessage}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Active Result Card with Spring Pop Reveal */}
          {result && !loading && (
            <div
              data-testid="scam-check-result"
              className={`mt-6 rounded-xl border p-6 transition-all animate-pop-in shadow-lg ${tierStyles.bg}`}
            >
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-black/5 pb-4">
                <div className="flex items-center gap-3">
                  {tierStyles.icon}
                  <div>
                    <span className="font-mono text-[10.5px] uppercase tracking-wider opacity-75">
                      Verdict Analysis
                    </span>
                    <h4 className="text-[17px] font-bold tracking-tight">
                      {tierStyles.label}
                    </h4>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <span className="font-mono text-[10.5px] uppercase tracking-wider opacity-75">
                      Threat Score
                    </span>
                    <span className="block font-mono text-xl font-bold">
                      {currentScore} / 100
                    </span>
                  </div>
                </div>
              </div>

              {/* Threat Score Bar */}
              <div className="mt-4 h-1.5 w-full rounded-full bg-black/10 overflow-hidden">
                <div
                  className="h-full rounded-full bg-accent transition-all duration-700 ease-out"
                  style={{ width: `${Math.max(6, currentScore)}%` }}
                />
              </div>

              {/* Reasons / Matched Indicators */}
              <div className="mt-5">
                <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink">
                  Identified Reasons &amp; Triggers:
                </span>
                <ul className="mt-2.5 space-y-2">
                  {currentReasons.map((reason, idx) => (
                    <li
                      key={idx}
                      className="flex items-start gap-2.5 text-[13.5px] text-ink"
                    >
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                      <span>{reason}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Recovery Guidance for Dangerous Verdict */}
              {currentTier === "DANGEROUS" && (
                <div className="mt-6 rounded-lg bg-card/90 p-4 border border-line shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-2 font-mono text-[12px] font-semibold text-accent">
                      <PhoneCall size={14} />
                      First-Hour Emergency Help
                    </span>
                    <a
                      href="https://cybercrime.gov.in"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 font-mono text-[11.5px] text-agent hover:underline"
                    >
                      cybercrime.gov.in
                      <ExternalLink size={12} />
                    </a>
                  </div>
                  <p className="mt-2 text-[12.5px] text-mute leading-relaxed">
                    If money was deducted, immediately dial National Cyber Crime
                    Helpline <strong className="text-ink">1930</strong> or notify your bank to freeze the beneficiary account.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Bottom Disclaimer */}
          <p className="mt-6 text-center text-[12px] text-faint">
            {liveDemo.disclaimer}
          </p>
        </div>

      </div>
    </section>
  );
}
