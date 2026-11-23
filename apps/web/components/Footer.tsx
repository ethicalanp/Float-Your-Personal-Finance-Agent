"use client";

import * as React from "react";
import Link from "next/link";
import { landingContent } from "@/content/landing";
import { Logo } from "@/components/Logo";
import { ArrowUpRight } from "lucide-react";

export function Footer() {
  const { finalCta, footer } = landingContent;

  return (
    <footer className="mt-20">
      {/* Final Call to Action Section */}
      <div className="mx-auto max-w-[1240px] px-5 md:px-8">
        <div className="relative overflow-hidden rounded-3xl bg-neutral-950 px-6 py-16 text-center text-white sm:px-12 md:py-24 shadow-2xl">
          {/* Background Atmospheric Glow */}
          <div
            className="absolute -top-32 left-1/2 -translate-x-1/2 h-96 w-96 rounded-full bg-accent/20 blur-3xl pointer-events-none"
            aria-hidden="true"
          />

          <div className="relative z-10 mx-auto max-w-[680px]">
            <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 font-mono text-[11px] uppercase tracking-wider text-white/90">
              <span className="h-2 w-2 rounded-full bg-accent" />
              <span>{finalCta.kicker}</span>
            </div>

            <h2 className="cnl-serif mt-6 text-[36px] leading-[1.08] tracking-tight sm:text-[50px] md:text-[60px]">
              {finalCta.title}
            </h2>

            <p className="mt-4 text-[15.5px] leading-relaxed text-white/70">
              {finalCta.description}
            </p>

            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link
                href={finalCta.ctaButton.href}
                className="cnl-pill is-lg bg-white text-black hover:bg-neutral-200 w-full sm:w-auto"
              >
                <span className="cnl-roll" data-t={finalCta.ctaButton.label}>
                  <span>{finalCta.ctaButton.label}</span>
                </span>
                <ArrowUpRight size={17} className="ml-1 opacity-75" />
              </Link>

              <a
                href={finalCta.secondaryButton.href}
                className="cnl-pill is-lg bg-white/10 text-white hover:bg-white/20 w-full sm:w-auto"
              >
                <span className="cnl-roll" data-t={finalCta.secondaryButton.label}>
                  <span>{finalCta.secondaryButton.label}</span>
                </span>
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* Main Footer Links & Branding */}
      <div className="mx-auto max-w-[1240px] px-5 pt-20 pb-12 md:px-8">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-12">

          {/* Brand Info */}
          <div className="md:col-span-5">
            <Logo size="lg" />
            <p className="mt-4 max-w-[340px] text-[13.5px] leading-relaxed text-mute">
              {footer.brandTagline}
            </p>
            <div className="mt-6 flex items-center gap-2 text-[12px] text-mute">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              <span>All protection engines operational</span>
            </div>
          </div>

          {/* Nav Columns */}
          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3 md:col-span-7">
            {footer.navColumns.map((col, idx) => (
              <div key={idx}>
                <h4 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-faint">
                  {col.title}
                </h4>
                <ul className="mt-4 space-y-2.5">
                  {col.links.map((link, lIdx) => (
                    <li key={lIdx}>
                      <a
                        href={link.href}
                        className="text-[13.5px] text-mute transition-colors hover:text-ink"
                      >
                        {link.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

        </div>

        {/* Large Decorative Masked Wordmark Watermark */}
        <div
          aria-hidden="true"
          className="mt-16 select-none overflow-hidden text-center opacity-[0.06] dark:opacity-[0.04]"
        >
          <span className="font-serif text-[clamp(100px,22vw,320px)] font-bold leading-none tracking-tighter">
            FLOAT
          </span>
        </div>

        {/* Legal Disclaimer & Bottom Row */}
        <div className="mt-6 border-t border-line pt-8">
          {/* Mandatory User Requirement Disclaimer */}
          <p className="rounded-lg bg-soft/60 p-4 text-center font-mono text-[11.5px] leading-relaxed text-mute">
            {footer.legalDisclaimer}
          </p>

          <div className="mt-6 flex flex-col items-center justify-between gap-4 text-[12.5px] text-faint sm:flex-row">
            <span>{footer.copyright}</span>
            <div className="flex gap-6">
              <a href="/privacy" className="hover:text-ink">
                Privacy
              </a>
              <a href="/terms" className="hover:text-ink">
                Terms
              </a>
              <a href="#security" className="hover:text-ink">
                Security
              </a>
            </div>
          </div>
        </div>

      </div>
    </footer>
  );
}
