"use client";

import { useEffect, useState } from "react";
import { Sun, Moon, Monitor } from "lucide-react";

export type ThemeMode = "light" | "dark" | "system";

export function getStoredTheme(): ThemeMode {
  if (typeof window === "undefined") return "system";
  return (localStorage.getItem("float_theme") as ThemeMode) || "system";
}

export function setAppTheme(newTheme: ThemeMode): void {
  if (typeof window === "undefined") return;

  localStorage.setItem("float_theme", newTheme);

  const isDark =
    newTheme === "dark" ||
    (newTheme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);

  document.documentElement.setAttribute("data-scheme", isDark ? "dark" : "light");
  if (isDark) {
    document.documentElement.classList.add("dark");
  } else {
    document.documentElement.classList.remove("dark");
  }

  window.dispatchEvent(new CustomEvent("float_theme_change", { detail: { theme: newTheme, isDark } }));
}

export function useTheme() {
  const [theme, setTheme] = useState<ThemeMode>("system");

  useEffect(() => {
    setTheme(getStoredTheme());

    function handleThemeChange(e: any) {
      if (e.detail?.theme) {
        setTheme(e.detail.theme);
      }
    }

    function handleSystemChange(e: MediaQueryListEvent) {
      if (getStoredTheme() === "system") {
        document.documentElement.setAttribute("data-scheme", e.matches ? "dark" : "light");
        if (e.matches) {
          document.documentElement.classList.add("dark");
        } else {
          document.documentElement.classList.remove("dark");
        }
      }
    }

    window.addEventListener("float_theme_change", handleThemeChange);
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    mediaQuery.addEventListener("change", handleSystemChange);

    return () => {
      window.removeEventListener("float_theme_change", handleThemeChange);
      mediaQuery.removeEventListener("change", handleSystemChange);
    };
  }, []);

  return { theme, setTheme: setAppTheme };
}

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  function cycleTheme() {
    if (theme === "system") setTheme("dark");
    else if (theme === "dark") setTheme("light");
    else setTheme("system");
  }

  return (
    <button
      onClick={cycleTheme}
      type="button"
      className="flex items-center gap-1.5 rounded-lg border border-line bg-card/60 px-2.5 py-1.5 text-xs font-medium text-mute transition-colors hover:bg-soft hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent"
      title={`Current theme: ${theme} (Click to switch)`}
      aria-label={`Toggle theme (currently ${theme})`}
      data-testid="theme-toggle"
    >
      {theme === "light" && <Sun className="h-3.5 w-3.5 text-amber-500" />}
      {theme === "dark" && <Moon className="h-3.5 w-3.5 text-indigo-400" />}
      {theme === "system" && <Monitor className="h-3.5 w-3.5 text-accent" />}
      <span className="capitalize">{theme}</span>
    </button>
  );
}
