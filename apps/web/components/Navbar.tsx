"use client";

import * as React from "react";
import Link from "next/link";
import { Logo } from "@/components/Logo";
import { landingContent } from "@/content/landing";
import ThemeToggle from "@/components/ThemeToggle";
import { Menu, X } from "lucide-react";

export function Navbar() {
  const [scrolled, setScrolled] = React.useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = React.useState(false);
  const [hoveredIdx, setHoveredIdx] = React.useState<number | null>(null);
  const { header } = landingContent;

  React.useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 16);
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <>
      <header
        role="banner"
        className={`sticky top-0 z-40 w-full transition-all duration-300 ${
          scrolled ? "cnl-nav-scrolled" : "bg-transparent"
        }`}
      >
        <div className="mx-auto flex h-[68px] max-w-[1240px] items-center justify-between px-5 md:px-8">
          {/* Logo Placeholder */}
          <Link
            href="/"
            className="flex items-center rounded-lg p-1 text-ink focus-visible:outline-2 focus-visible:outline-agent"
          >
            <Logo />
          </Link>

          {/* Desktop Nav Links with Smooth Hover Capsule */}
          <nav
            aria-label="Main Navigation"
            onMouseLeave={() => setHoveredIdx(null)}
            className="relative hidden items-center gap-1 rounded-full p-1 md:flex"
          >
            {header.navLinks.map((link, idx) => (
              <a
                key={link.label}
                href={link.href}
                onMouseEnter={() => setHoveredIdx(idx)}
                className={`relative z-10 inline-flex h-9 items-center rounded-full px-4 text-[13.5px] font-medium transition-colors duration-200 ${
                  hoveredIdx === idx ? "text-ink" : "text-mute hover:text-ink"
                } focus-visible:outline-2 focus-visible:outline-agent`}
              >
                {hoveredIdx === idx && (
                  <span
                    className="absolute inset-0 -z-10 rounded-full bg-soft/80 shadow-sm animate-fade-in"
                    aria-hidden="true"
                  />
                )}
                <span>{link.label}</span>
              </a>
            ))}
          </nav>

          {/* Action CTAs & Theme Toggle */}
          <div className="hidden items-center gap-3 md:flex">
            <ThemeToggle />
            <Link
              href={header.loginHref}
              className="text-[13.5px] font-medium text-mute transition-colors duration-200 hover:text-ink focus-visible:outline-2 focus-visible:outline-agent"
            >
              {header.loginText}
            </Link>
            <Link
              href={header.signupHref}
              className="cnl-pill focus-visible:outline-2 focus-visible:outline-agent"
            >
              <span className="cnl-roll" data-t={header.signupText}>
                <span>{header.signupText}</span>
              </span>
            </Link>
          </div>

          {/* Mobile Menu Trigger */}
          <button
            type="button"
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileMenuOpen}
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-soft text-ink transition-transform hover:scale-105 focus-visible:outline-2 focus-visible:outline-agent md:hidden"
          >
            {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </header>

      {/* Accessible Mobile Menu Sheet */}
      {mobileMenuOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Navigation Menu"
          className="fixed inset-0 z-50 flex flex-col bg-bg p-6 md:hidden animate-fade-in"
        >
          <div className="flex items-center justify-between">
            <Logo />
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setMobileMenuOpen(false)}
              className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-soft text-ink"
            >
              <X size={20} />
            </button>
          </div>

          <div className="mt-12 flex flex-col gap-6">
            {header.navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                onClick={() => setMobileMenuOpen(false)}
                className="font-serif text-3xl font-medium tracking-tight text-ink transition-colors hover:text-accent"
              >
                {link.label}
              </a>
            ))}
          </div>

          <div className="mt-auto flex flex-col gap-3 pb-8">
            <div className="flex items-center justify-between pb-2 border-b border-line">
              <span className="text-xs text-mute font-medium">Appearance</span>
              <ThemeToggle />
            </div>
            <Link
              href={header.loginHref}
              onClick={() => setMobileMenuOpen(false)}
              className="flex h-12 w-full items-center justify-center rounded-full border border-line text-[15px] font-medium text-ink"
            >
              {header.loginText}
            </Link>
            <Link
              href={header.signupHref}
              onClick={() => setMobileMenuOpen(false)}
              className="cnl-pill is-lg w-full text-center"
            >
              {header.signupText}
            </Link>
          </div>
        </div>
      )}
    </>
  );
}
