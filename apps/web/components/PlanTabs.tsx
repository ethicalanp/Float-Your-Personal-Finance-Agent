"use client";

import { useRef, type KeyboardEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Calculator, PieChart, Repeat } from "lucide-react";

interface PlanTabsProps {
  tabsLabel: string;
  budgetLabel: string;
  recurringLabel: string;
  calculatorsLabel?: string;
  onBeforeNavigate?: () => void;
}

type TabKey = "budget" | "recurring" | "calculators";
const TAB_ORDER: TabKey[] = ["budget", "recurring", "calculators"];

export default function PlanTabs({
  tabsLabel,
  budgetLabel,
  recurringLabel,
  calculatorsLabel = "Calculators",
  onBeforeNavigate,
}: PlanTabsProps) {
  const pathname = usePathname();
  const router = useRouter();
  const refs = useRef<Record<TabKey, HTMLButtonElement | null>>({
    budget: null,
    recurring: null,
    calculators: null,
  });

  const activeTab: TabKey = pathname.startsWith("/plan/recurring")
    ? "recurring"
    : pathname.startsWith("/plan/calculators")
    ? "calculators"
    : "budget";

  function navigateTo(target: TabKey) {
    if (target === activeTab) return;
    onBeforeNavigate?.();
    router.push(target === "budget" ? "/plan" : `/plan/${target}`);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const idx = TAB_ORDER.indexOf(activeTab);
    let next: TabKey | null = null;
    if (e.key === "ArrowRight") next = TAB_ORDER[(idx + 1) % TAB_ORDER.length];
    else if (e.key === "ArrowLeft") next = TAB_ORDER[(idx - 1 + TAB_ORDER.length) % TAB_ORDER.length];
    else if (e.key === "Home") next = TAB_ORDER[0];
    else if (e.key === "End") next = TAB_ORDER[TAB_ORDER.length - 1];
    if (next) {
      e.preventDefault();
      refs.current[next]?.focus();
      navigateTo(next);
    }
  }

  const tabs: { key: TabKey; label: string; Icon: typeof PieChart }[] = [
    { key: "budget", label: budgetLabel, Icon: PieChart },
    { key: "recurring", label: recurringLabel, Icon: Repeat },
    { key: "calculators", label: calculatorsLabel, Icon: Calculator },
  ];

  return (
    <div
      role="tablist"
      aria-label={tabsLabel}
      onKeyDown={handleKeyDown}
      data-testid="plan-tablist"
      className="grid grid-cols-3 w-full sm:inline-flex sm:w-auto rounded-2xl border border-line bg-soft/60 p-1 gap-1"
    >
      {tabs.map(({ key, label, Icon }) => {
        const selected = activeTab === key;
        return (
          <button
            key={key}
            ref={(el) => {
              refs.current[key] = el;
            }}
            type="button"
            role="tab"
            id={`tab-${key}`}
            aria-selected={selected}
            aria-controls={`panel-${key}`}
            tabIndex={selected ? 0 : -1}
            data-testid={`tab-${key}`}
            onClick={() => navigateTo(key)}
            className={`inline-flex items-center justify-center gap-2 rounded-xl px-3 sm:px-4 py-2 text-xs sm:text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
              selected
                ? "bg-card text-ink font-semibold shadow-sm border border-line/60"
                : "text-mute hover:text-ink"
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
