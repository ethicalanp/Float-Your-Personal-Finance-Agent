"use client";

import { useRef, type KeyboardEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Landmark, PieChart, Repeat, Scissors, Shield, Target } from "lucide-react";

interface PlanTabsProps {
  tabsLabel?: string;
  budgetLabel?: string;
  recurringLabel?: string;
  goalsLabel?: string;
  emergencyLabel?: string;
  subscriptionsLabel?: string;
  netWorthLabel?: string;
  onBeforeNavigate?: () => void;
}

type TabKey = "budget" | "recurring" | "goals" | "emergency" | "subscriptions" | "net-worth";

const TAB_ORDER: TabKey[] = ["budget", "recurring", "goals", "emergency", "subscriptions", "net-worth"];

export default function PlanTabs({
  tabsLabel = "Plan sections",
  budgetLabel = "Budget",
  recurringLabel = "Recurring & bills",
  goalsLabel = "Goals",
  emergencyLabel = "Emergency fund",
  subscriptionsLabel = "Subscriptions",
  netWorthLabel = "Net worth",
  onBeforeNavigate,
}: PlanTabsProps) {
  const pathname = usePathname();
  const router = useRouter();
  const refs = useRef<Record<TabKey, HTMLButtonElement | null>>({
    budget: null,
    recurring: null,
    goals: null,
    emergency: null,
    subscriptions: null,
    "net-worth": null,
  });

  const activeTab: TabKey = pathname.startsWith("/plan/recurring")
    ? "recurring"
    : pathname.startsWith("/plan/goals")
      ? "goals"
      : pathname.startsWith("/plan/emergency-fund")
        ? "emergency"
        : pathname.startsWith("/plan/subscriptions")
          ? "subscriptions"
          : pathname.startsWith("/plan/net-worth")
            ? "net-worth"
            : "budget";

  const tabs: { key: TabKey; href: string; label: string; Icon: typeof PieChart }[] = [
    { key: "budget", href: "/plan", label: budgetLabel, Icon: PieChart },
    { key: "recurring", href: "/plan/recurring", label: recurringLabel, Icon: Repeat },
    { key: "goals", href: "/plan/goals", label: goalsLabel, Icon: Target },
    { key: "emergency", href: "/plan/emergency-fund", label: emergencyLabel, Icon: Shield },
    { key: "subscriptions", href: "/plan/subscriptions", label: subscriptionsLabel, Icon: Scissors },
    { key: "net-worth", href: "/plan/net-worth", label: netWorthLabel, Icon: Landmark },
  ];

  function navigateTo(target: TabKey) {
    if (target === activeTab) return;
    onBeforeNavigate?.();
    const match = tabs.find((t) => t.key === target);
    if (match) router.push(match.href);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const idx = TAB_ORDER.indexOf(activeTab);
    let next: TabKey | null = null;
    if (e.key === "ArrowRight") {
      next = TAB_ORDER[(idx + 1) % TAB_ORDER.length];
    } else if (e.key === "ArrowLeft") {
      next = TAB_ORDER[(idx - 1 + TAB_ORDER.length) % TAB_ORDER.length];
    } else if (e.key === "Home") {
      next = TAB_ORDER[0];
    } else if (e.key === "End") {
      next = TAB_ORDER[TAB_ORDER.length - 1];
    }
    if (next) {
      e.preventDefault();
      refs.current[next]?.focus();
      navigateTo(next);
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
      {tabs.map(({ key, label, Icon }) => {
        const isActive = activeTab === key;
        return (
          <button
            key={key}
            ref={(el) => {
              refs.current[key] = el;
            }}
            type="button"
            role="tab"
            id={`tab-${key}`}
            aria-selected={isActive}
            aria-controls={`panel-${key}`}
            tabIndex={isActive ? 0 : -1}
            data-testid={`tab-${key}`}
            onClick={() => navigateTo(key)}
            className={`inline-flex items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-xs sm:text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
              isActive ? "bg-card text-ink font-semibold shadow-sm border border-line/60" : "text-mute hover:text-ink"
            }`}
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span className="truncate">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
