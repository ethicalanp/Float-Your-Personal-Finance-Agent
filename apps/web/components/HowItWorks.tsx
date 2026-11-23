"use client";

import * as React from "react";
import { landingContent } from "@/content/landing";

export function HowItWorks() {
  const { howItWorks } = landingContent;

  return (
    <section id="how-it-works" className="py-20 md:py-32 bg-soft/30">
      <div className="mx-auto max-w-[1240px] px-5 md:px-8">

        {/* Header */}
        <div className="flex flex-col items-center text-center">
          <div className="cnl-kicker">{howItWorks.kicker}</div>
          <h2 className="cnl-serif mt-4 text-[34px] leading-tight text-ink sm:text-[46px] md:text-[54px]">
            {howItWorks.title}
          </h2>
          <p className="mt-4 max-w-[620px] text-[15.5px] leading-relaxed text-mute">
            {howItWorks.description}
          </p>
        </div>

        {/* Steps Grid */}
        <div className="mt-16 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {howItWorks.steps.map((step, idx) => (
            <div
              key={idx}
              className="group relative flex flex-col justify-between rounded-xl border border-line bg-card p-6 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-md"
            >
              <div>
                <span className="font-mono text-2xl font-light text-faint group-hover:text-accent transition-colors">
                  {step.step}
                </span>
                <h3 className="mt-4 text-[17px] font-semibold tracking-tight text-ink">
                  {step.title}
                </h3>
                <p className="mt-3 text-[13.5px] leading-relaxed text-mute">
                  {step.description}
                </p>
              </div>

              <div className="mt-6 border-t border-line/60 pt-3">
                <span className="font-mono text-[11px] text-agent">
                  {step.actionNote}
                </span>
              </div>
            </div>
          ))}
        </div>

      </div>
    </section>
  );
}
