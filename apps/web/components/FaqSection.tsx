"use client";

import * as React from "react";
import { landingContent } from "@/content/landing";
import { ChevronDown } from "lucide-react";

export function FaqSection() {
  const { faq } = landingContent;
  const [openIndex, setOpenIndex] = React.useState<number | null>(0);

  const toggleIndex = (idx: number) => {
    setOpenIndex(openIndex === idx ? null : idx);
  };

  return (
    <section id="faq" className="py-20 md:py-32">
      <div className="mx-auto max-w-[840px] px-5 md:px-8">

        {/* Header */}
        <div className="flex flex-col items-center text-center">
          <div className="cnl-kicker">{faq.kicker}</div>
          <h2 className="cnl-serif mt-4 text-[34px] leading-tight text-ink sm:text-[46px] md:text-[54px]">
            {faq.title}
          </h2>
          <p className="mt-4 max-w-[560px] text-[15.5px] leading-relaxed text-mute">
            {faq.description}
          </p>
        </div>

        {/* Accordion List */}
        <div className="mt-14 divide-y divide-line border-y border-line">
          {faq.items.map((item, idx) => {
            const isOpen = openIndex === idx;
            return (
              <div key={idx} className="py-4">
                <button
                  type="button"
                  id={`faq-btn-${idx}`}
                  aria-expanded={isOpen}
                  aria-controls={`faq-panel-${idx}`}
                  onClick={() => toggleIndex(idx)}
                  className="flex w-full items-center justify-between py-2 text-left text-[16px] font-medium text-ink transition-colors hover:text-accent focus-visible:outline-2 focus-visible:outline-agent"
                >
                  <span className="pr-4">{item.question}</span>
                  <ChevronDown
                    size={18}
                    className={`shrink-0 text-faint transition-transform duration-300 ${
                      isOpen ? "rotate-180 text-ink" : ""
                    }`}
                  />
                </button>

                <div
                  id={`faq-panel-${idx}`}
                  role="region"
                  aria-labelledby={`faq-btn-${idx}`}
                  className={`grid transition-[grid-template-rows] duration-300 ease-editorial ${
                    isOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
                  }`}
                >
                  <div className="overflow-hidden">
                    <p className="pt-2 pb-4 text-[14.5px] leading-relaxed text-mute">
                      {item.answer}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

      </div>
    </section>
  );
}
