"use client";

import * as React from "react";
import { landingContent } from "@/content/landing";
import { Lock, EyeOff, Shield, Database } from "lucide-react";

export function SecuritySection() {
  const { security } = landingContent;

  const icons = [
    <EyeOff key="1" size={20} className="text-agent" />,
    <Lock key="2" size={20} className="text-accent" />,
    <Shield key="3" size={20} className="text-emerald-600" />,
    <Database key="4" size={20} className="text-ink" />,
  ];

  return (
    <section id="security" className="py-20 md:py-32 bg-soft/20">
      <div className="mx-auto max-w-[1240px] px-5 md:px-8">

        {/* Header */}
        <div className="flex flex-col items-center text-center">
          <div className="cnl-kicker">{security.kicker}</div>
          <h2 className="cnl-serif mt-4 text-[34px] leading-tight text-ink sm:text-[46px] md:text-[54px]">
            {security.title}
          </h2>
          <p className="mt-4 max-w-[620px] text-[15.5px] leading-relaxed text-mute">
            {security.description}
          </p>
        </div>

        {/* Safeguards Grid */}
        <div className="mt-16 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {security.statements.map((statement, idx) => (
            <div
              key={idx}
              className="rounded-xl border border-line bg-card p-6 shadow-sm transition-all duration-300 hover:shadow-md"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-soft">
                {icons[idx % icons.length]}
              </div>

              <h3 className="mt-5 text-[16px] font-semibold tracking-tight text-ink">
                {statement.title}
              </h3>

              <p className="mt-2.5 text-[13.5px] leading-relaxed text-mute">
                {statement.description}
              </p>
            </div>
          ))}
        </div>

      </div>
    </section>
  );
}
