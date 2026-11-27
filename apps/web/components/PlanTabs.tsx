"use client";

import { useRef, type KeyboardEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import { PieChart, Repeat } from "lucide-react";

interface PlanTabsProps {
  tabsLabel: string;
  budgetLabel: string;
  recurringLabel: string;
  onBeforeNavigate?: () => void;
}

export default function PlanTabs({
  tabsLabel,
  budgetLabel,
  recurringLabel,
  onBeforeNavigate,
}: PlanTabsProps) {
  const pathname = usePathname();
  const router = useRouter();
  const budgetRef = useRef<HTMLButtonElement | null>(null);
  const recurringRef = useRef<HTMLButtonElement | null>(null);

  const activeTab: "budget" | "recurring" = pathname.startsWith("/plan/recurring")
    ? "recurring"
    : "budget";

  function navigateTo(target: "budget" | "recurring") {
    if (target === activeTab) return;
    onBeforeNavigate?.();
    router.push(target === "budget" ? "/plan" : "/plan/recurring");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const next = activeTab === "budget" ? "recurring" : "budget";
      (next === "budget" ? budgetRef.current : recurringRef.current)?.focus();
      navigateTo(next);
    } else if (e.key === "Home") {
      e.preventDefault();
      budgetRef.current?.focus();
      navigateTo("budget");
    } else if (e.key === "End") {
      e.preventDefault();
      recurringRef.current?.focus();
      navigateTo("recurring");
    }
  }

  return (
    <div
      role="tablist"
      aria-label={tabsLabel}
      onKeyDown={handleKeyDown}
      data-testid="plan-tablist"
      className="grid grid-cols-2 w-full sm:inline-flex sm:w-auto rounded-2xl border border-line bg-soft/60 p-1 gap-1"
    >
      <button
        ref={budgetRef}
        type="button"
        role="tab"
        id="tab-budget"
        aria-selected={activeTab === "budget"}
        aria-controls="panel-budget"
        tabIndex={activeTab === "budget" ? 0 : -1}
        data-testid="tab-budget"
        onClick={() => navigateTo("budget")}
        className={`inline-flex items-center justify-center gap-2 rounded-xl px-3 sm:px-4 py-2 text-xs sm:text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
          activeTab === "budget"
            ? "bg-card text-ink font-semibold shadow-sm border border-line/60"
            : "text-mute hover:text-ink"
        }`}
      >
        <PieChart className="h-4 w-4 shrink-0" />
        <span className="truncate">{budgetLabel}</span>
      </button>

      <button
        ref={recurringRef}
        type="button"
        role="tab"
        id="tab-recurring"
        aria-selected={activeTab === "recurring"}
        aria-controls="panel-recurring"
        tabIndex={activeTab === "recurring" ? 0 : -1}
        data-testid="tab-recurring"
        onClick={() => navigateTo("recurring")}
        className={`inline-flex items-center justify-center gap-2 rounded-xl px-3 sm:px-4 py-2 text-xs sm:text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
          activeTab === "recurring"
            ? "bg-card text-ink font-semibold shadow-sm border border-line/60"
            : "text-mute hover:text-ink"
        }`}
      >
        <Repeat className="h-4 w-4 shrink-0" />
        <span className="truncate">{recurringLabel}</span>
      </button>
    </div>
  );
}
