"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Script from "next/script";
import { AlertCircle } from "lucide-react";

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: {
          initialize: (config: {
            client_id: string;
            callback: (response: { credential?: string }) => void;
            auto_select?: boolean;
            cancel_on_tap_outside?: boolean;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            options: {
              type?: "standard" | "icon";
              theme?: "outline" | "filled_blue" | "filled_black";
              size?: "large" | "medium" | "small";
              text?: "signin_with" | "signup_with" | "continue_with" | "signin";
              shape?: "rectangular" | "pill" | "circle" | "square";
              logo_alignment?: "left" | "center";
              width?: number;
              locale?: string;
            }
          ) => void;
        };
      };
    };
  }
}

export interface GoogleSignInButtonProps {
  clientId?: string | null;
  onCredential: (idToken: string) => void | Promise<void>;
  onError?: (message: string) => void;
  text?: "signin_with" | "signup_with" | "continue_with" | "signin";
  disabled?: boolean;
  dataTestId?: string;
}

// Module-level coordination prevents double google.accounts.id.initialize() in StrictMode
// while always routing responses to the currently mounted instance.
let initializedClientId: string | null = null;
let activeCredentialHandler: ((response: { credential?: string }) => void) | null = null;

function isDarkScheme(): boolean {
  if (typeof document === "undefined") return false;
  const el = document.documentElement;
  return el.classList.contains("dark") || el.getAttribute("data-scheme") === "dark";
}

function getGisLocale(): string {
  if (typeof document === "undefined") return "en";
  const lang = (document.documentElement.lang || "en").toLowerCase();
  if (lang === "manglish") return "en";
  return lang || "en";
}

export function GoogleSignInButton({
  clientId,
  onCredential,
  onError,
  text = "continue_with",
  disabled = false,
  dataTestId = "google-login-btn",
}: GoogleSignInButtonProps) {
  const resolvedClientId = (process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || clientId || "").trim();

  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const onCredentialRef = useRef(onCredential);
  const onErrorRef = useRef(onError);
  onCredentialRef.current = onCredential;
  onErrorRef.current = onError;

  const [scriptLoaded, setScriptLoaded] = useState(false);
  const [scriptBlocked, setScriptBlocked] = useState(false);
  const [buttonRendered, setButtonRendered] = useState(false);
  const [isDark, setIsDark] = useState(false);
  const [locale, setLocale] = useState("en");
  const [containerWidth, setContainerWidth] = useState(340);

  // Detect theme and language changes
  useEffect(() => {
    setIsDark(isDarkScheme());
    setLocale(getGisLocale());

    const handleThemeChange = () => setIsDark(isDarkScheme());
    const handleLangChange = () => setLocale(getGisLocale());

    window.addEventListener("float_theme_change", handleThemeChange);
    window.addEventListener("float_lang_change", handleLangChange);

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    mediaQuery.addEventListener("change", handleThemeChange);

    const observer = new MutationObserver(() => {
      setIsDark(isDarkScheme());
      setLocale(getGisLocale());
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-scheme", "lang"],
    });

    return () => {
      window.removeEventListener("float_theme_change", handleThemeChange);
      window.removeEventListener("float_lang_change", handleLangChange);
      mediaQuery.removeEventListener("change", handleThemeChange);
      observer.disconnect();
    };
  }, []);

  // Track responsive container width (clamped to GIS max 400px)
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;

    const updateWidth = () => {
      const measured = Math.floor(el.getBoundingClientRect().width || el.clientWidth || 340);
      const clamped = Math.min(400, Math.max(220, measured));
      setContainerWidth(clamped);
    };

    updateWidth();
    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(updateWidth);
      ro.observe(el);
      return () => ro.disconnect();
    }
  }, []);

  // Detect already-loaded GIS script or offline/blocked timeout
  useEffect(() => {
    if (!resolvedClientId) return;
    if (window.google?.accounts?.id) {
      setScriptLoaded(true);
      setScriptBlocked(false);
      return;
    }
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      setScriptBlocked(true);
      return;
    }

    const timer = window.setTimeout(() => {
      if (!window.google?.accounts?.id) {
        setScriptBlocked(true);
      }
    }, 6000);

    return () => window.clearTimeout(timer);
  }, [resolvedClientId]);

  const renderGisButton = useCallback(() => {
    const gis = window.google?.accounts?.id;
    const container = containerRef.current;
    if (!gis || !container || !resolvedClientId) return;

    const handler = (response: { credential?: string }) => {
      if (response?.credential) {
        void onCredentialRef.current(response.credential);
      } else {
        onErrorRef.current?.("Google sign-in was cancelled or returned no credential.");
      }
    };
    activeCredentialHandler = handler;

    try {
      if (initializedClientId !== resolvedClientId) {
        gis.initialize({
          client_id: resolvedClientId,
          callback: (response) => {
            activeCredentialHandler?.(response);
          },
          auto_select: false,
          cancel_on_tap_outside: true,
        });
        initializedClientId = resolvedClientId;
      }

      container.innerHTML = "";
      gis.renderButton(container, {
        type: "standard",
        theme: isDark ? "filled_black" : "outline",
        size: "large",
        text,
        shape: "rectangular",
        logo_alignment: "left",
        width: containerWidth,
        locale,
      });
      setButtonRendered(true);
      setScriptBlocked(false);
    } catch {
      setScriptBlocked(true);
    }
  }, [resolvedClientId, isDark, text, containerWidth, locale]);

  useEffect(() => {
    if (!scriptLoaded && !window.google?.accounts?.id) return;
    const containerEl = containerRef.current;
    renderGisButton();

    return () => {
      if (containerEl) {
        containerEl.innerHTML = "";
      }
      activeCredentialHandler = null;
    };
  }, [scriptLoaded, renderGisButton]);

  if (!resolvedClientId) {
    return (
      <div
        data-testid={dataTestId}
        className="w-full max-w-[400px] rounded-xl border border-line bg-soft/60 px-4 py-2.5 text-center text-xs text-mute"
      >
        Google Sign-In is not configured for this environment. Please use email or phone.
      </div>
    );
  }

  return (
    <div ref={wrapperRef} data-testid={dataTestId} className="w-full max-w-[400px] flex flex-col items-center">
      <Script
        id="google-gsi-client"
        src="https://accounts.google.com/gsi/client"
        strategy="afterInteractive"
        onLoad={() => {
          setScriptLoaded(true);
          setScriptBlocked(false);
        }}
        onError={() => {
          setScriptBlocked(true);
        }}
      />

      {scriptBlocked ? (
        <div
          role="status"
          data-testid="google-signin-blocked"
          className="flex w-full items-center gap-2 rounded-xl border border-line bg-soft/70 px-3.5 py-2.5 text-xs text-mute"
        >
          <AlertCircle className="h-4 w-4 shrink-0 text-amber-500" />
          <span>
            Google Sign-In could not load (blocked by adblocker or offline). Email sign-in remains available below.
          </span>
        </div>
      ) : (
        <div
          className={`relative flex w-full justify-center min-h-[44px] ${
            disabled ? "pointer-events-none opacity-60" : ""
          }`}
        >
          {!buttonRendered && (
            <div
              data-testid="google-signin-loading"
              className="flex h-[44px] w-full items-center justify-center rounded-lg border border-line bg-soft/60 text-xs font-medium text-mute"
            >
              Loading Google Sign-In…
            </div>
          )}
          <div
            ref={containerRef}
            id="google-gis-container"
            className={buttonRendered ? "flex justify-center" : "sr-only"}
          />
        </div>
      )}
    </div>
  );
}
