"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertCircle, RefreshCw, Home } from "lucide-react";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log client error with non-sensitive metadata
    console.error("Client error boundary caught:", error);
  }, [error]);

  const requestId = error.digest || "";

  return (
    <div className="min-h-screen bg-bg text-ink flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-6 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-red-50 text-red-600 dark:bg-red-950/50 dark:text-red-400">
          <AlertCircle className="h-7 w-7" />
        </div>

        <div className="space-y-2">
          <h2 className="text-2xl font-serif font-medium text-ink">
            Something Went Wrong
          </h2>
          <p className="text-xs text-mute leading-relaxed">
            We encountered an unexpected problem while loading this page. Your data remains secure.
          </p>
          {requestId && (
            <p className="text-[11px] font-mono text-faint bg-soft/50 rounded-lg p-2 mt-2">
              Reference ID: {requestId}
            </p>
          )}
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
          <button
            onClick={() => reset()}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-xs font-semibold text-bg hover:opacity-90 transition-all shadow-sm"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Try Again</span>
          </button>

          <Link
            href="/home"
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-line bg-soft/40 px-4 py-2.5 text-xs font-semibold text-ink hover:bg-soft transition-all"
          >
            <Home className="h-4 w-4" />
            <span>Go to Home</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
