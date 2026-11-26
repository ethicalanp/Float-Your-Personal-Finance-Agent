"use client";

import { useEffect, useState, useRef } from "react";
import { usePathname } from "next/navigation";
import { X, Smartphone, ArrowDownToLine } from "lucide-react";

const EXCLUDED_ROUTES = [
  "/download",
  "/login",
  "/signup",
  "/terms",
  "/privacy",
  "/security",
  "/forgot-password",
  "/reset-password",
  "/verify-email",
];

const DISMISS_KEY = "float_get_app_dismissed_until";
const SESSION_SHOWN_KEY = "float_get_app_session_shown";
const FOURTEEN_DAYS_MS = 14 * 24 * 60 * 60 * 1000;

export function GetAppPrompt() {
  const pathname = usePathname();
  const [isVisible, setIsVisible] = useState(false);
  const initialMountPath = useRef<string | null>(null);

  // Check exclusion rules
  const isExcludedRoute = (path: string | null) => {
    if (!path) return true;
    return EXCLUDED_ROUTES.some((excluded) => path === excluded || path.startsWith(`${excluded}/`));
  };

  useEffect(() => {
    // Record the first screen of the visit
    if (initialMountPath.current === null) {
      initialMountPath.current = pathname;
      return; // Do NOT show on the first screen of a visit
    }

    // Don't show if route is excluded or user stayed on the same initial path
    if (isExcludedRoute(pathname)) {
      setIsVisible(false);
      return;
    }

    // Check 14-day dismissal in localStorage (safe try/catch)
    try {
      const dismissedUntil = localStorage.getItem(DISMISS_KEY);
      if (dismissedUntil && Number(dismissedUntil) > Date.now()) {
        return;
      }
    } catch {
      // localStorage unavailable / sandboxed
    }

    // Check session limit (at most once per session)
    try {
      const alreadyShown = sessionStorage.getItem(SESSION_SHOWN_KEY);
      if (alreadyShown === "true") {
        return;
      }
    } catch {
      // sessionStorage unavailable
    }

    // If all checks pass, show prompt and mark session as shown
    try {
      sessionStorage.setItem(SESSION_SHOWN_KEY, "true");
    } catch {
      // ignore
    }
    setIsVisible(true);
  }, [pathname]);

  // Keyboard accessibility: Escape closes the prompt
  useEffect(() => {
    if (!isVisible) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        handleDismiss();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isVisible]);

  function handleDismiss() {
    setIsVisible(false);
    try {
      localStorage.setItem(DISMISS_KEY, (Date.now() + FOURTEEN_DAYS_MS).toString());
    } catch {
      // ignore
    }
  }

  if (!isVisible) return null;

  const androidApkUrl = process.env.NEXT_PUBLIC_ANDROID_APK_URL;

  return (
    <aside
      aria-label="Get the Float mobile app"
      data-testid="get-app-prompt"
      className="fixed bottom-0 inset-x-0 z-50 p-4 sm:p-6 pointer-events-none flex justify-center motion-reduce:transition-none"
    >
      <div className="pointer-events-auto w-full max-w-lg rounded-2xl border border-line bg-card/95 backdrop-blur-md p-4 sm:p-5 shadow-2xl transition-all duration-300 ease-out flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent">
              <Smartphone className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-ink">Get the Float App</h3>
              <p className="text-xs text-mute mt-0.5">
                Financial planning, scam alerts &amp; borrow readiness on your phone.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleDismiss}
            aria-label="Dismiss app prompt"
            className="rounded-lg p-1.5 text-mute hover:bg-soft hover:text-ink transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center gap-2 pt-1 border-t border-line/60">
          {androidApkUrl ? (
            <a
              href={androidApkUrl}
              download
              className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-ink text-bg px-3.5 py-2 text-xs font-semibold hover:opacity-90 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <ArrowDownToLine className="h-3.5 w-3.5" />
              <span>Download APK</span>
            </a>
          ) : (
            <button
              type="button"
              disabled
              className="flex-1 flex items-center justify-center gap-1.5 rounded-xl bg-soft text-mute px-3.5 py-2 text-xs font-medium cursor-not-allowed"
            >
              <span>Android: Coming soon</span>
            </button>
          )}

          <button
            type="button"
            disabled
            className="flex-1 flex items-center justify-center gap-1.5 rounded-xl bg-soft text-mute px-3.5 py-2 text-xs font-medium cursor-not-allowed"
          >
            <span>iOS: Coming soon</span>
          </button>
        </div>
      </div>
    </aside>
  );
}

export default GetAppPrompt;
