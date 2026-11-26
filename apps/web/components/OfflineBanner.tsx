"use client";

import { useState, useEffect } from "react";
import { WifiOff } from "lucide-react";

export default function OfflineBanner() {
  const [isOffline, setIsOffline] = useState(false);

  useEffect(() => {
    function handleOnline() {
      setIsOffline(false);
    }
    function handleOffline() {
      setIsOffline(true);
    }

    if (typeof window !== "undefined") {
      setIsOffline(!navigator.onLine);
      window.addEventListener("online", handleOnline);
      window.addEventListener("offline", handleOffline);
    }

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  if (!isOffline) return null;

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="sticky top-0 z-50 flex items-center justify-center gap-2 bg-amber-500 px-4 py-2 text-xs font-semibold text-black shadow-md transition-all"
    >
      <WifiOff className="h-4 w-4" />
      <span>You are currently offline. Changes requiring network connection are paused.</span>
    </div>
  );
}
