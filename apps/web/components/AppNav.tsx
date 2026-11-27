"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Home,
  ShieldAlert,
  CreditCard,
  MessageSquare,
  Settings,
  User,
  LogOut,
  Eye,
  EyeOff,
  ChevronDown,
} from "lucide-react";
import { Logo } from "./Logo";
import ThemeToggle from "./ThemeToggle";
import { Language, getActiveLanguage, setActiveLanguage } from "@/lib/i18n";

const NAV_ITEMS = [
  { href: "/home", label: "Home", icon: Home },
  { href: "/protect", label: "Protect", icon: ShieldAlert },
  { href: "/borrow", label: "Borrow", icon: CreditCard },
  { href: "/assistant", label: "Assistant", icon: MessageSquare },
  { href: "/profile", label: "Profile", icon: User },
];

export default function AppNav() {
  const pathname = usePathname();
  const router = useRouter();
  const [hideAmounts, setHideAmounts] = useState(false);
  const [lang, setLang] = useState<Language>("en");
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setProfileMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    function handleOutsideClick(e: MouseEvent) {
      if (profileMenuRef.current && !profileMenuRef.current.contains(e.target as Node)) {
        setProfileMenuOpen(false);
      }
    }
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setProfileMenuOpen(false);
    }
    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  useEffect(() => {
    const isHidden = localStorage.getItem("float_hide_amounts") === "true";
    setHideAmounts(isHidden);
    setLang(getActiveLanguage());

    function handlePrivacyToggle(e: any) {
      if (typeof e.detail?.hide === "boolean") {
        setHideAmounts(e.detail.hide);
      }
    }
    window.addEventListener("float_privacy_toggle", handlePrivacyToggle);
    return () => window.removeEventListener("float_privacy_toggle", handlePrivacyToggle);
  }, []);

  function togglePrivacyAmounts() {
    const newVal = !hideAmounts;
    setHideAmounts(newVal);
    localStorage.setItem("float_hide_amounts", String(newVal));
    window.dispatchEvent(new CustomEvent("float_privacy_toggle", { detail: { hide: newVal } }));
  }

  function handleLanguageChange(newLang: Language) {
    setLang(newLang);
    setActiveLanguage(newLang);
    window.location.reload();
  }

  async function handleLogout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
      if (typeof BroadcastChannel !== "undefined") {
        const channel = new BroadcastChannel("float_auth_sync");
        channel.postMessage({ type: "LOGOUT" });
        channel.close();
      }
      router.push("/login");
      router.refresh();
    } catch {
      router.push("/login");
    }
  }

  return (
    <>
      {/* Top Header for Desktop & Tablet */}
      <header className="sticky top-0 z-40 w-full border-b border-line bg-bg/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link href="/home" className="flex items-center gap-2">
            <Logo />
          </Link>

          {/* Desktop Nav Links */}
          <nav className="hidden items-center gap-1 md:flex">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
              if (item.href === "/profile") {
                return (
                  <div key={item.href} ref={profileMenuRef} className="relative flex items-center">
                    <Link
                      href="/profile"
                      className={`flex items-center gap-2 rounded-l-lg px-3 py-2 text-sm font-medium transition-colors ${
                        isActive
                          ? "bg-soft text-ink font-semibold"
                          : "text-mute hover:bg-soft/60 hover:text-ink"
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                      <span>{item.label}</span>
                    </Link>
                    <button
                      type="button"
                      onClick={() => setProfileMenuOpen((v) => !v)}
                      aria-label="Profile menu"
                      aria-haspopup="menu"
                      aria-expanded={profileMenuOpen}
                      data-testid="profile-menu-btn"
                      className={`rounded-r-lg px-1.5 py-2 text-sm transition-colors ${
                        isActive
                          ? "bg-soft text-ink"
                          : "text-mute hover:bg-soft/60 hover:text-ink"
                      }`}
                    >
                      <ChevronDown className="h-3.5 w-3.5" />
                    </button>
                    {profileMenuOpen && (
                      <div
                        role="menu"
                        aria-label="Profile menu options"
                        className="absolute right-0 top-full mt-1.5 w-44 rounded-xl border border-line bg-card p-1.5 shadow-lg z-50"
                      >
                        <Link
                          href="/profile"
                          role="menuitem"
                          className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                            pathname === "/profile"
                              ? "bg-soft text-ink font-semibold"
                              : "text-mute hover:bg-soft hover:text-ink"
                          }`}
                        >
                          <User className="h-3.5 w-3.5" />
                          <span>Profile</span>
                        </Link>
                        <Link
                          href="/profile/settings"
                          role="menuitem"
                          data-testid="profile-menu-settings"
                          className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                            pathname === "/profile/settings"
                              ? "bg-soft text-ink font-semibold"
                              : "text-mute hover:bg-soft hover:text-ink"
                          }`}
                        >
                          <Settings className="h-3.5 w-3.5" />
                          <span>Settings</span>
                        </Link>
                      </div>
                    )}
                  </div>
                );
              }
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-soft text-ink font-semibold"
                      : "text-mute hover:bg-soft/60 hover:text-ink"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          {/* Controls: Privacy Toggle, Language, Theme, Logout */}
          <div className="flex items-center gap-2">
            {/* Privacy amount masking */}
            <button
              onClick={togglePrivacyAmounts}
              type="button"
              className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-mute transition-colors hover:bg-soft hover:text-ink"
              title={hideAmounts ? "Show financial amounts" : "Hide financial amounts (Privacy mode)"}
              aria-label={hideAmounts ? "Show financial amounts" : "Hide financial amounts"}
              data-testid="privacy-amounts-toggle"
            >
              {hideAmounts ? (
                <>
                  <EyeOff className="h-3.5 w-3.5 text-accent" />
                  <span className="hidden sm:inline">Hidden</span>
                </>
              ) : (
                <>
                  <Eye className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">Visible</span>
                </>
              )}
            </button>

            {/* Language Switcher */}
            <div className="relative inline-flex items-center">
              <select
                value={lang}
                onChange={(e) => handleLanguageChange(e.target.value as Language)}
                className="h-8 rounded-lg border border-line bg-bg px-2 text-xs font-medium text-ink focus:outline-none focus:ring-1 focus:ring-accent"
                aria-label="Select language"
                data-testid="language-select"
              >
                <option value="en">English</option>
                <option value="ml">മലയാളം (Draft)</option>
                <option value="manglish">Manglish (Draft)</option>
              </select>
            </div>

            {/* Theme Toggle */}
            <ThemeToggle />

            {/* Logout */}
            <button
              onClick={handleLogout}
              className="hidden items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-mute transition-colors hover:bg-soft hover:text-ink md:flex"
              title="Log out"
              aria-label="Log out"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span>Log out</span>
            </button>
          </div>
        </div>
      </header>

      {/* Bottom Navigation for Mobile (Works down to 360px viewport) */}
      <nav
        aria-label="Mobile Navigation"
        className="fixed bottom-0 left-0 right-0 z-50 flex h-16 items-center justify-around border-t border-line bg-bg/95 px-2 backdrop-blur-lg md:hidden"
      >
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex flex-col items-center justify-center py-1 text-center transition-colors ${
                isActive ? "text-accent font-semibold" : "text-mute hover:text-ink"
              }`}
            >
              <Icon className="h-5 w-5" />
              <span className="mt-1 text-[10px] leading-none">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </>
  );
}
