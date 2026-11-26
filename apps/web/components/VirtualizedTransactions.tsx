"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import { formatINR, formatISTDate } from "@/lib/i18n";
import { ArrowUpRight, ArrowDownLeft } from "lucide-react";

export interface TransactionItem {
  id: string;
  transaction_date: string;
  amount: number;
  direction: "inflow" | "outflow";
  category: string;
  description: string;
}

interface VirtualizedTransactionsProps {
  transactions: TransactionItem[];
  hideAmounts?: boolean;
  itemHeight?: number;
  viewportHeight?: number;
}

/**
 * High-performance virtualized transaction list rendering only the visible slice
 * to handle hundreds or thousands of imported transactions without DOM bloat.
 */
export default function VirtualizedTransactions({
  transactions,
  hideAmounts = false,
  itemHeight = 64,
  viewportHeight = 384, // 6 items visible
}: VirtualizedTransactionsProps) {
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const totalCount = transactions.length;
  const totalHeight = totalCount * itemHeight;

  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - 2);
  const endIndex = Math.min(
    totalCount - 1,
    Math.floor((scrollTop + viewportHeight) / itemHeight) + 2
  );

  const visibleItems = useMemo(() => {
    const items = [];
    for (let i = startIndex; i <= endIndex; i++) {
      if (transactions[i]) {
        items.push({ index: i, item: transactions[i] });
      }
    }
    return items;
  }, [transactions, startIndex, endIndex]);

  function handleScroll(e: React.UIEvent<HTMLDivElement>) {
    setScrollTop(e.currentTarget.scrollTop);
  }

  if (transactions.length === 0) {
    return (
      <div className="py-8 text-center text-xs text-mute">
        No transaction records found for this period.
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      style={{ height: viewportHeight }}
      className="overflow-y-auto border-t border-line divide-y divide-line pr-1"
      tabIndex={0}
      aria-label="Transaction list (virtualized scroll)"
      role="region"
    >
      <div style={{ height: totalHeight, position: "relative" }}>
        {visibleItems.map(({ index, item }) => {
          const topPosition = index * itemHeight;
          const isInflow = item.direction === "inflow";

          return (
            <div
              key={item.id || index}
              style={{
                position: "absolute",
                top: topPosition,
                left: 0,
                right: 0,
                height: itemHeight,
              }}
              className="flex items-center justify-between px-3 py-2 text-xs hover:bg-soft/40 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                    isInflow
                      ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400"
                      : "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400"
                  }`}
                >
                  {isInflow ? (
                    <ArrowDownLeft className="h-4 w-4" />
                  ) : (
                    <ArrowUpRight className="h-4 w-4" />
                  )}
                </div>
                <div className="min-w-0">
                  <p className="font-medium text-ink truncate max-w-[200px] sm:max-w-xs">
                    {item.description || item.category || "Transaction"}
                  </p>
                  <p className="text-[10px] text-faint">
                    {formatISTDate(item.transaction_date, "short")} • {item.category}
                  </p>
                </div>
              </div>

              <div className="text-right shrink-0">
                <span
                  className={`font-mono text-xs font-semibold ${
                    isInflow
                      ? "text-emerald-600 dark:text-emerald-400"
                      : "text-ink"
                  }`}
                >
                  {isInflow ? "+" : "-"}
                  {formatINR(item.amount, { hideAmount: hideAmounts })}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
