import { Navbar } from "@/components/Navbar";
import { Hero } from "@/components/Hero";
import { ThreePillars } from "@/components/ThreePillars";
import { HowItWorks } from "@/components/HowItWorks";
import { LiveScamDemo } from "@/components/LiveScamDemo";
import { SecuritySection } from "@/components/SecuritySection";
import { FaqSection } from "@/components/FaqSection";
import { Footer } from "@/components/Footer";

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col bg-bg text-ink selection:bg-accent/20">
      {/* Header with Navigation and Logo Placeholder */}
      <Navbar />

      <main className="flex-1">
        {/* Hero Section with India financial focus & abstract code mock */}
        <Hero />

        {/* Three Pillars: Plan, Protect, Borrow */}
        <ThreePillars />

        {/* How it works: 4-step progression */}
        <HowItWorks />

        {/* Live Scam Check Demo Box */}
        <LiveScamDemo />

        {/* Honest Privacy & Security Safeguards */}
        <SecuritySection />

        {/* Accessible FAQ Accordion */}
        <FaqSection />
      </main>

      {/* Final CTA & Footer with Mandatory Legal Disclaimer */}
      <Footer />
    </div>
  );
}
