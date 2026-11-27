"use client";

import { useRef, type KeyboardEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import { PieChart, Repeat, Target, Shield } from "lucide-react";

interface PlanTabsProps {
  tabsLabel?: string;
  budgetLabel?: string;
  recurringLabel?: string;
  goalsLabel?: string;
  emergencyLabel?: string;
  onBeforeNavigate?: () => void;
}

type TabKey = "budget" | "recurring" | "goals" | "emergency";

export default function PlanTabs({
  tabsLabel = "Plan sections",
  budgetLabel = "Budget",
  recurringLabel = "Recurring & bills",
  goalsLabel = "Goals",
  emergencyLabel = "Emergency fund",
  onBeforeNavigate,
}: PlanTabsProps) {
  const pathname = usePathname();
  const router = useRouter();
  const refs = useRef<Record<TabKey, HTMLButtonElement | null>>({
    budget: null,
    recurring: null,
    goals: null,
    emergency: null,
  });

  const activeTab: TabKey = pathname.startsWith("/plan/recurring")
    ? "recurring"
    : pathname.startsWith("/plan/goals")
      ? "goals"
      : pathname.startsWith("/plan/emergency-fund")
        ? "emergency"
        : "budget";

  const tabs: { key: TabKey; href: string; label: string; icon: typeof PieChart }[] = [
    { key: "budget", href: "/plan", label: budgetLabel, icon: PieChart },
    { key: "recurring", href: "/plan/recurring", label: recurringLabel, icon: Repeat },
    { key: "goals", href: "/plan/goals", label: goalsLabel, icon: Target },
    { key: "emergency", href: "/plan/emergency-fund", label: emergencyLabel, icon: Shield },
  ];

  function navigateTo(target: TabKey) {
    if (target === activeTab) return;
    onBeforeNavigate?.();
    const match = tabs.find((t) => t.key === target);
    if (match) router.push(match.href);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const idx = tabs.findIndex((t) => t.key === activeTab);
    if (e.key === "ArrowRight") {
      e.preventDefault();
      const next = tabs[(idx + 1) % tabs.length].key;
      refs.current[next]?.focus();
      navigateTo(next);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const next = tabs[(idx - 1 + tabs.length) % tabs.length].key;
      refs.current[next]?.focus();
      navigateTo(next);
    } else if (e.key === "Home") {
      e.preventDefault();
      refs.current.budget?.focus();
      navigateTo("budget");
    } else if (e.key === "End") {
      e.preventDefault();
      refs.current.emergency?.focus();
      navigateTo("emergency");
    }
  }

  return (
    <div
      role="tablist"
      aria-label={tabsLabel}
      onKeyDown={handleKeyDown}
      data-testid="plan-tablist"
      className="grid grid-cols-2 sm:inline-flex sm:w-auto w-full rounded-2xl border border-line bg-soft/60 p-1 gap-1"
    >
      {tabs.map((t) => {
        const Icon = t.icon;
        const isActive = activeTab === t.key;
        return (
          <button
            key={t.key}
            ref={(el) => {
              refs.current[t.key] = el;
            }}
            type="button"
            role="tab"
            id={`tab-${t.key}`}
            aria-selected={isActive}
            aria-controls={`panel-${t.key}`}
            tabIndex={isActive ? 0 : -1}
            data-testid={`tab-${t.key}`}
            onClick={() => navigateTo(t.key)}
            className={`inline-flex items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-xs sm:text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
              isActive ? "bg-card text-ink font-semibold shadow-sm border border-line/60" : "text-mute hover:text-ink"
            }`}
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span className="truncate">{t.label}</span>
          </button>
        );
      })}
    </div>
  );
}
