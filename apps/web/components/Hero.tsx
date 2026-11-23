"use client";

import * as React from "react";
import Link from "next/link";
import { landingContent } from "@/content/landing";
import {
  ShieldAlert,
  ArrowUpRight,
  CheckCircle2,
  TrendingUp,
  AlertOctagon,
  Sparkles,
} from "lucide-react";

interface Scenario {
  id: string;
  chipLabel: string;
  tag: string;
  title: string;
  badge: string;
  badgeColor: string;
  sampleText: string;
  indicators: string[];
}

const SCENARIOS: Scenario[] = [
  {
    id: "kseb",
    chipLabel: "Electricity Phishing (Manglish)",
    tag: "Malayalam + Manglish Threat",
    title: "Urgent Disconnection Scam",
    badge: "Dangerous",
    badgeColor: "bg-red-500/10 text-accent",
    sampleText:
      "Dear customer, your electricity power will be disconnected at 9:30 PM. Call 9876543210 or install KSEB.apk",
    indicators: [
      "Artificial urgency pressuring payment before verification",
      "Unauthorized third-party APK installation link",
      "Helpline 1930 & recovery draft immediately accessible",
    ],
  },
  {
    id: "upi",
    chipLabel: "UPI Reward Trap",
    tag: "Payment Impersonation",
    title: "Fake Cashback Authorization",
    badge: "Critical",
    badgeColor: "bg-red-500/10 text-accent",
    sampleText:
      "Congratulations! You won Rs 4,999 cashback reward on PhonePe. Click link to receive direct bank transfer.",
    indicators: [
      "Deceptive 'receive money' reverse-debit request",
      "Demands PIN to 'accept' incoming funds",
      "Official bank reporting draft generated",
    ],
  },
  {
    id: "cashflow",
    chipLabel: "Smart Cash Flow",
    tag: "Monthly Statement Analysis",
    title: "Income & Liability Balance",
    badge: "Healthy",
    badgeColor: "bg-emerald-500/10 text-emerald-600",
    sampleText:
      "Monthly inflows: ₹64,000 | Fixed outflows: ₹18,400 | Discretionary: ₹9,120 | Buffer: 2.4 months",
    indicators: [
      "End-to-end masked account & transaction identifiers",
      "Zero unverified credit pushes or high-interest traps",
      "Transparent borrowing readiness view with plain reasons",
    ],
  },
];

export function Hero() {
  const { hero } = landingContent;
  const headlines = hero.headline.split("\n");

  const [activeScenarioIdx, setActiveScenarioIdx] = React.useState(0);
  const [isPaused, setIsPaused] = React.useState(false);

  // Mouse parallax state for depth drift
  const [drift, setDrift] = React.useState({ x: 0, y: 0 });

  // Auto-cycle scenarios every 5 seconds unless hovered
  React.useEffect(() => {
    if (isPaused) return;
    const timer = setInterval(() => {
      setActiveScenarioIdx((prev) => (prev + 1) % SCENARIOS.length);
    }, 5200);
    return () => clearInterval(timer);
  }, [isPaused]);

  const activeScenario = SCENARIOS[activeScenarioIdx];

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const xRatio = (e.clientX - rect.left) / rect.width - 0.5;
    const yRatio = (e.clientY - rect.top) / rect.height - 0.5;
    setDrift({
      x: Math.round(xRatio * 16),
      y: Math.round(yRatio * 10),
    });
  };

  const handleMouseLeave = () => {
    setDrift({ x: 0, y: 0 });
    setIsPaused(false);
  };

  return (
    <section className="relative pt-6 pb-20 md:pt-12 md:pb-28">
      {/* Hero Text Header */}
      <div className="mx-auto flex max-w-[860px] flex-col items-center px-5 text-center">
        {/* Kicker badge */}
        <div className="mb-6 inline-flex items-center gap-2 rounded-full bg-soft px-3.5 py-1 text-[11px] font-medium tracking-wide uppercase text-ink transition-transform hover:scale-105">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
          </span>
          <span className="font-mono">{hero.kicker}</span>
        </div>

        {/* Serif Headline with Masked Staggered Rise Reveal */}
        <h1 className="font-serif text-[42px] leading-[1.04] tracking-[-0.03em] text-ink sm:text-[58px] md:text-[74px]">
          {headlines.map((line, idx) => (
            <span key={idx} className="cnl-title-line">
              <span
                className="cnl-line-in"
                style={{ animationDelay: `${idx * 130}ms` }}
              >
                {line}
              </span>
            </span>
          ))}
        </h1>

        {/* Subtitle */}
        <p className="mt-6 max-w-[620px] text-[15.5px] leading-relaxed text-mute sm:text-[17px] animate-fade-in">
          {hero.subheadline}
        </p>

        {/* Dual CTAs */}
        <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:gap-4">
          <Link
            href={hero.primaryCta.href}
            className="cnl-pill is-lg w-full sm:w-auto"
          >
            <span className="cnl-roll" data-t={hero.primaryCta.label}>
              <span>{hero.primaryCta.label}</span>
            </span>
            <ArrowUpRight size={17} className="ml-1 opacity-80" />
          </Link>

          <a
            href={hero.secondaryCta.href}
            className="cnl-pill is-lg is-secondary w-full sm:w-auto"
          >
            <span className="cnl-roll" data-t={hero.secondaryCta.label}>
              <span>{hero.secondaryCta.label}</span>
            </span>
          </a>
        </div>

        <p className="mt-4 font-mono text-[11.5px] tracking-wide text-faint">
          {hero.pillNote}
        </p>
      </div>

      {/* Abstract Product Illustration / Interactive Vista with Parallax */}
      <div className="mx-auto mt-12 max-w-[1180px] px-4 sm:px-6">
        <div
          onMouseMove={handleMouseMove}
          onMouseEnter={() => setIsPaused(true)}
          onMouseLeave={handleMouseLeave}
          className="cnl-vista relative min-h-[500px] w-full rounded-2xl md:min-h-[580px] transition-shadow duration-500 hover:shadow-2xl"
        >
          {/* Layer 1: Procedural Mountain Ridges drifting subtly */}
          <div
            className="absolute inset-0 transition-transform duration-300 ease-out"
            style={{
              transform: `translate3d(${drift.x * -0.6}px, ${drift.y * -0.6}px, 0)`,
            }}
          >
            <svg
              className="h-full w-full object-cover"
              viewBox="0 0 1600 900"
              preserveAspectRatio="xMidYMid slice"
              aria-hidden="true"
            >
              <defs>
                <linearGradient id="skyGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#cfd9df" />
                  <stop offset="70%" stopColor="#e2ebf0" />
                  <stop offset="100%" stopColor="#d5dcd6" />
                </linearGradient>
              </defs>
              <rect width="1600" height="900" fill="url(#skyGrad)" />
              {/* Distant ridge */}
              <path
                d="M0,900 L0,510 Q400,440 800,520 T1600,480 L1600,900 Z"
                fill="#98a89f"
                opacity="0.5"
              />
              {/* Mid ridge */}
              <path
                d="M0,900 L0,590 Q350,520 750,590 T1600,560 L1600,900 Z"
                fill="#75887c"
                opacity="0.75"
              />
              {/* Near ridge */}
              <path
                d="M0,900 L0,680 Q500,600 1000,670 T1600,630 L1600,900 Z"
                fill="#52685c"
                opacity="0.9"
              />
              {/* Foreground terrain */}
              <path
                d="M0,900 L0,770 Q450,710 900,770 T1600,740 L1600,900 Z"
                fill="#34463d"
              />
            </svg>
          </div>

          {/* Layer 2: Vignette shade */}
          <div className="cnl-vista-shade" />

          {/* Top Live Status Indicator */}
          <div className="absolute top-4 right-4 z-20 flex items-center gap-2 rounded-full bg-black/45 px-3.5 py-1.5 backdrop-blur-md shadow-md">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            <span className="font-mono text-[11px] font-medium tracking-wide text-white">
              Float Engine &middot; Real-time Shield
            </span>
          </div>

          {/* Floating Cards with Opposite Depth Drift */}
          <div
            className="relative z-10 flex min-h-[500px] w-full flex-col items-center justify-center p-6 md:min-h-[580px] transition-transform duration-300 ease-out"
            style={{
              transform: `translate3d(${drift.x * 0.8}px, ${drift.y * 0.8}px, 0)`,
            }}
          >
            <div className="grid w-full max-w-[920px] grid-cols-1 gap-6 md:grid-cols-2">

              {/* Card A: Dynamic Scenario Card with Animated Morph */}
              <div
                key={activeScenario.id}
                className="cnl-card cnl-float-a animate-pop-in overflow-hidden p-6 shadow-2xl backdrop-blur-xl transition-all"
              >
                <div className="flex items-center justify-between border-b border-black/5 pb-3">
                  <div className="flex items-center gap-2.5">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-red-100 text-accent">
                      {activeScenario.id === "cashflow" ? (
                        <TrendingUp size={16} className="text-agent" />
                      ) : (
                        <ShieldAlert size={16} />
                      )}
                    </span>
                    <div>
                      <h4 className="text-[13.5px] font-semibold text-ink">
                        {activeScenario.title}
                      </h4>
                      <p className="font-mono text-[10.5px] text-faint">
                        {activeScenario.tag}
                      </p>
                    </div>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${activeScenario.badgeColor}`}
                  >
                    {activeScenario.badge}
                  </span>
                </div>

                <div className="mt-4 rounded-xl bg-soft/70 p-3.5 text-[12.5px] leading-relaxed text-ink font-mono border border-line/40">
                  &ldquo;{activeScenario.sampleText}&rdquo;
                </div>

                <div className="mt-4 space-y-2 text-[12px] text-mute">
                  {activeScenario.indicators.map((ind, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                      <span>{ind}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Card B: Cash Flow Intelligence & Buffer Card */}
              <div className="cnl-card cnl-float-b p-6 shadow-2xl backdrop-blur-xl transition-all">
                <div className="flex items-center justify-between border-b border-black/5 pb-3">
                  <div className="flex items-center gap-2.5">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-agent">
                      <TrendingUp size={16} />
                    </span>
                    <div>
                      <h4 className="text-[13.5px] font-semibold text-ink">
                        Cash Flow Intelligence
                      </h4>
                      <p className="font-mono text-[10.5px] text-faint">
                        Parsed from Statement &middot; Masked
                      </p>
                    </div>
                  </div>
                  <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-bold text-emerald-600 uppercase tracking-wider">
                    Positive
                  </span>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-xl bg-soft/60 p-3 transition-colors hover:bg-soft">
                    <span className="block font-mono text-[10.5px] text-mute">
                      Fixed Monthly Outflows
                    </span>
                    <span className="mt-1 block font-mono text-lg font-semibold text-ink">
                      ₹18,400
                    </span>
                  </div>
                  <div className="rounded-xl bg-soft/60 p-3 transition-colors hover:bg-soft">
                    <span className="block font-mono text-[10.5px] text-mute">
                      Discretionary Spending
                    </span>
                    <span className="mt-1 block font-mono text-lg font-semibold text-ink">
                      ₹9,120
                    </span>
                  </div>
                </div>

                <div className="mt-4 flex items-center justify-between rounded-xl border border-line bg-card/70 px-3.5 py-2.5 text-[12px] shadow-sm">
                  <span className="flex items-center gap-2 text-mute">
                    <CheckCircle2 size={15} className="text-emerald-500" />
                    Borrow Readiness
                  </span>
                  <span className="font-mono text-[11.5px] font-semibold text-ink">
                    Adequate 30-day cushion
                  </span>
                </div>
              </div>

            </div>

            {/* Scenario Navigation Chips at bottom of Vista */}
            <div className="mt-8 flex flex-wrap justify-center gap-2">
              {SCENARIOS.map((s, idx) => {
                const isCurrent = idx === activeScenarioIdx;
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setActiveScenarioIdx(idx)}
                    className={`relative rounded-full px-3.5 py-1 text-[11.5px] font-medium transition-all duration-300 backdrop-blur-md ${
                      isCurrent
                        ? "bg-white text-black shadow-md scale-105"
                        : "bg-black/35 text-white/80 hover:bg-black/50 hover:text-white"
                    }`}
                  >
                    <span>{s.chipLabel}</span>
                  </button>
                );
              })}
            </div>

          </div>
        </div>
      </div>
    </section>
  );
}
