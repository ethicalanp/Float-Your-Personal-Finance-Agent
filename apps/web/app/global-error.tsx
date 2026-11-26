"use client";

import { AlertOctagon, RefreshCw } from "lucide-react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#f7f7f5] text-[#111211] dark:bg-[#0c0d0d] dark:text-[#efeeea] flex items-center justify-center p-4">
        <div className="w-full max-w-md rounded-3xl border border-black/10 dark:border-white/10 bg-white dark:bg-[#151716] p-8 shadow-sm space-y-6 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-red-100 text-red-600 dark:bg-red-950 dark:text-red-400">
            <AlertOctagon className="h-7 w-7" />
          </div>

          <div className="space-y-2">
            <h1 className="text-2xl font-serif font-medium">Critical Application Error</h1>
            <p className="text-xs text-neutral-600 dark:text-neutral-400 leading-relaxed">
              An unrecoverable system error occurred. Please refresh the page to restore your session.
            </p>
            {error.digest && (
              <p className="text-[11px] font-mono text-neutral-500 bg-neutral-100 dark:bg-neutral-800 rounded p-2">
                Request ID: {error.digest}
              </p>
            )}
          </div>

          <button
            onClick={() => reset()}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#111211] text-[#f7f7f5] dark:bg-[#efeeea] dark:text-[#111211] px-4 py-2.5 text-xs font-semibold hover:opacity-90 transition-all shadow-sm"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Reload Application</span>
          </button>
        </div>
      </body>
    </html>
  );
}
