"use client";

import React, { useEffect, useState, useRef } from "react";
import AppNav from "./AppNav";
import { AlertTriangle, Clock } from "lucide-react";

interface AppShellProps {
  children: React.ReactNode;
}

const IDLE_TIMEOUT_MS = 15 * 60 * 1000; // 15 minutes
const WARNING_DURATION_MS = 60 * 1000; // 1 minute warning before logout

export default function AppShell({ children }: AppShellProps) {
  const [showIdleWarning, setShowIdleWarning] = useState(false);
  const [secondsRemaining, setSecondsRemaining] = useState(60);
  const lastActivityRef = useRef<number>(Date.now());
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // 1. Back-Forward Cache (bfcache) mitigation for logged-out pages
  useEffect(() => {
    function onPageShow(event: PageTransitionEvent) {
      if (event.persisted) {
        window.location.reload();
      }
    }
    window.addEventListener("pageshow", onPageShow);
    return () => window.removeEventListener("pageshow", onPageShow);
  }, []);

  // 2. Cross-tab logout synchronization via BroadcastChannel
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel("float_auth_sync");

    channel.onmessage = (event) => {
      if (event.data?.type === "LOGOUT") {
        window.location.href = "/login?reason=logged_out";
      }
    };

    return () => {
      channel.close();
    };
  }, []);

  // 3. User activity tracker & Idle timeout detection
  useEffect(() => {
    function resetActivity() {
      lastActivityRef.current = Date.now();
      if (showIdleWarning) {
        setShowIdleWarning(false);
      }
    }

    const events = ["mousedown", "keydown", "touchstart", "scroll", "wheel"];
    for (const evt of events) {
      window.addEventListener(evt, resetActivity, { passive: true });
    }

    const interval = setInterval(() => {
      const now = Date.now();
      const elapsed = now - lastActivityRef.current;

      if (elapsed >= IDLE_TIMEOUT_MS) {
        // Log out immediately after idle + warning timeout
        if (typeof BroadcastChannel !== "undefined") {
          const ch = new BroadcastChannel("float_auth_sync");
          ch.postMessage({ type: "LOGOUT" });
          ch.close();
        }
        window.location.href = "/login?reason=idle_timeout";
      } else if (elapsed >= IDLE_TIMEOUT_MS - WARNING_DURATION_MS) {
        setShowIdleWarning(true);
        const rem = Math.max(0, Math.ceil((IDLE_TIMEOUT_MS - elapsed) / 1000));
        setSecondsRemaining(rem);
      } else {
        setShowIdleWarning(false);
      }
    }, 1000);

    return () => {
      clearInterval(interval);
      for (const evt of events) {
        window.removeEventListener(evt, resetActivity);
      }
    };
  }, [showIdleWarning]);

  function handleStayLoggedIn() {
    lastActivityRef.current = Date.now();
    setShowIdleWarning(false);
  }

  return (
    <div className="min-h-screen bg-bg text-ink flex flex-col">
      <AppNav />

      {/* Idle Session Expiration Warning Modal */}
      {showIdleWarning && (
        <div
          role="alertdialog"
          aria-labelledby="idle-warning-title"
          aria-describedby="idle-warning-desc"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-fade-in"
        >
          <div className="w-full max-w-sm rounded-2xl border border-line bg-card p-6 shadow-xl space-y-4 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-amber-100 text-amber-600 dark:bg-amber-950/60 dark:text-amber-400">
              <Clock className="h-6 w-6" />
            </div>
            <h3 id="idle-warning-title" className="text-lg font-serif font-semibold text-ink">
              Are you still there?
            </h3>
            <p id="idle-warning-desc" className="text-xs text-mute leading-relaxed">
              For your financial privacy, your session will automatically lock in{" "}
              <strong className="text-ink font-semibold">{secondsRemaining} seconds</strong> due to inactivity.
            </p>
            <button
              onClick={handleStayLoggedIn}
              className="w-full rounded-xl bg-ink px-4 py-2.5 text-xs font-semibold text-bg hover:opacity-90 transition-all shadow-sm"
            >
              Stay Logged In
            </button>
          </div>
        </div>
      )}

      <main id="main-content" tabIndex={-1} className="flex-1 pb-20 md:pb-12 focus:outline-none">
        <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
          {children}
        </div>
      </main>
    </div>
  );
}
