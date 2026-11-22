"use client";

import * as React from "react";
import { landingContent } from "@/content/landing";
import { Check, ShieldCheck, Wallet, Gauge } from "lucide-react";

export function ThreePillars() {
  const { pillarsSection } = landingContent;
  const [activePillar, setActivePillar] = React.useState<"plan" | "protect" | "borrow">("protect");

  const icons = {
    plan: <Wallet size={18} className="text-agent" />,
    protect: <ShieldCheck size={18} className="text-accent" />,
    borrow: <Gauge size={18} className="text-emerald-500" />,
  };

  const selected =
    pillarsSection.pillars.find((p) => p.id === activePillar) ||
    pillarsSection.pillars[0];

  return (
    <section id="features" className="py-20 md:py-32">
      <div className="mx-auto max-w-[1240px] px-5 md:px-8">
        {/* Section Header */}
        <div className="flex flex-col items-center text-center">
          <div className="cnl-kicker">{pillarsSection.kicker}</div>
          <h2 className="cnl-serif mt-4 text-[34px] leading-tight text-ink sm:text-[46px] md:text-[54px]">
            {pillarsSection.title}
          </h2>
          <p className="mt-4 max-w-[620px] text-[15.5px] leading-relaxed text-mute">
            {pillarsSection.description}
          </p>
        </div>

        {/* Tab Selector Capsule */}
        <div className="mt-12 flex justify-center">
          <div className="inline-flex rounded-full bg-soft p-1.5 shadow-inner">
            {pillarsSection.pillars.map((pillar) => {
              const isCurrent = pillar.id === activePillar;
              return (
                <button
                  key={pillar.id}
                  type="button"
                  onClick={() => setActivePillar(pillar.id)}
                  className={`relative flex items-center gap-2 rounded-full px-5 py-2 text-[13.5px] font-medium transition-all duration-300 ${
                    isCurrent
                      ? "bg-card text-ink shadow-sm scale-105"
                      : "text-mute hover:text-ink hover:bg-card/40"
                  }`}
                >
                  {icons[pillar.id]}
                  <span>{pillar.title}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Selected Pillar Detailed Card with Staged Reveal */}
        <div
          key={selected.id}
          className="relative mt-10 overflow-hidden rounded-2xl border border-line bg-card p-6 shadow-xl transition-all duration-500 animate-pop-in md:p-12"
        >
          {/* Subtle Top Accent Progress Line */}
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-line overflow-hidden">
            <div className="h-full bg-accent w-full origin-left animate-fade-in" />
          </div>

          <div className="grid grid-cols-1 gap-10 lg:grid-cols-12 lg:items-center">

            {/* Left Column: Descriptions & Verified Capabilities */}
            <div className="lg:col-span-7">
              <span className="font-mono text-[11px] font-semibold tracking-widest text-accent uppercase">
                {selected.tag}
              </span>
              <h3 className="cnl-serif mt-2 text-[28px] text-ink sm:text-[38px]">
                {selected.subtitle}
              </h3>
              <p className="mt-4 text-[15px] leading-relaxed text-mute">
                {selected.description}
              </p>

              <div className="mt-8 space-y-3">
                {selected.features.map((feature, idx) => (
                  <div
                    key={idx}
                    className="flex items-start gap-3 text-[14px] text-ink transition-transform hover:translate-x-1 duration-200"
                  >
                    <span className="mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-soft text-agent">
                      <Check size={12} strokeWidth={3} />
                    </span>
                    <span>{feature}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Right Column: Code-Drawn UI Preview */}
            <div className="lg:col-span-5">
              <div className="rounded-xl border border-line bg-soft/50 p-5 md:p-6 transition-transform duration-300 hover:shadow-lg">
                <div className="flex items-center justify-between border-b border-line pb-3">
                  <span className="font-mono text-[11px] font-semibold uppercase text-faint">
                    Live Telemetry Preview
                  </span>
                  <span className="font-mono text-[11px] text-agent">
                    {selected.title} Module
                  </span>
                </div>

                <div className="mt-4 space-y-3">
                  {selected.mockData.map((item, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between rounded-lg bg-card p-3.5 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-md"
                    >
                      <div>
                        <span className="block text-[11px] font-medium text-mute">
                          {item.label}
                        </span>
                        <span className="mt-0.5 block font-mono text-[13.5px] font-semibold text-ink">
                          {item.detail}
                        </span>
                      </div>
                      {item.badge && (
                        <span className="rounded-full bg-soft px-2.5 py-1 font-mono text-[10.5px] font-medium text-ink">
                          {item.badge}
                        </span>
                      )}
                    </div>
                  ))}
                </div>

                <p className="mt-4 font-mono text-[11px] text-mute text-center">
                  100% transparent algorithmic rules &middot; User controlled
                </p>
              </div>
            </div>

          </div>
        </div>

      </div>
    </section>
  );
}
