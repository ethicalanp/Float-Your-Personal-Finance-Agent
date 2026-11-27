import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("Component States - Home screen supports skeleton, empty, error, and success states", () => {
  const homePath = path.join(process.cwd(), "app", "home", "page.tsx");
  const content = fs.readFileSync(homePath, "utf-8");

  assert.ok(content.includes("home-skeleton"), "Home must contain skeleton loading state");
  assert.ok(content.includes("home-empty-state"), "Home must contain empty state");
  assert.ok(content.includes("role=\"alert\""), "Home must render accessible error alert");
  assert.ok(content.includes("uploadSuccess"), "Home must render upload success state");
  assert.ok(content.includes("duplicateWarning"), "Home must render duplicate statement warning");
  assert.ok(content.includes("cancelUpload"), "Home must provide upload cancel capability");
  assert.ok(content.includes("VirtualizedTransactions"), "Home must integrate virtualized transaction list");
});

test("Component States - Borrow screen supports skeleton, empty, error, and statutory disclaimer", () => {
  const borrowPath = path.join(process.cwd(), "app", "borrow", "page.tsx");
  const content = fs.readFileSync(borrowPath, "utf-8");

  assert.ok(content.includes("borrow-skeleton"), "Borrow must contain skeleton loading state");
  assert.ok(content.includes("insufficient_data"), "Borrow must handle insufficient transaction history state");
  assert.ok(content.includes("Assessment Model Temporarily Unavailable"), "Borrow must handle 503 unavailable state");
  assert.ok(content.includes("disclaimer"), "Borrow must render mandatory indicative statutory disclaimer");
});

test("Component States - Assistant screen supports aria-live, suggested prompts, and DPDP consent banner", () => {
  const assistantPath = path.join(process.cwd(), "app", "assistant", "page.tsx");
  const content = fs.readFileSync(assistantPath, "utf-8");

  assert.ok(content.includes("aria-live=\"polite\""), "Assistant must have aria-live message container");
  assert.ok(content.includes("SUGGESTED_QUESTIONS"), "Assistant must present suggested questions for empty state");
  assert.ok(content.includes("AI Processing Consent Needed"), "Assistant must present DPDP consent banner when consent is missing");
});

test("Component States - Protect screen supports scam check, recovery lifecycle, and verified helplines", () => {
  const protectPath = path.join(process.cwd(), "app", "protect", "page.tsx");
  const content = fs.readFileSync(protectPath, "utf-8");

  assert.ok(content.includes("checkScam"), "Protect must invoke scam check API");
  assert.ok(content.includes("1930"), "Protect must present 1930 cyber fraud emergency helpline");
  assert.ok(content.includes("loadRecoveryCases"), "Protect must handle recovery cases lifecycle");
});

test("Theme System - Synchronous blocking script in <head> prevents theme flash", () => {
  const layoutPath = path.join(process.cwd(), "app", "layout.tsx");
  const content = fs.readFileSync(layoutPath, "utf-8");

  assert.ok(content.includes("THEME_SCRIPT"), "RootLayout must define THEME_SCRIPT");
  assert.ok(content.includes("<script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />"), "Must inject blocking script in head");
  assert.ok(content.includes("suppressHydrationWarning"), "<html> must have suppressHydrationWarning");
  assert.ok(content.includes("data-scheme"), "THEME_SCRIPT must set data-scheme on documentElement");
  assert.ok(content.includes("prefers-color-scheme"), "THEME_SCRIPT must respect prefers-color-scheme");
});

test("Theme System - Controls exist on Navbar, AppNav, and Settings", () => {
  const navContent = fs.readFileSync(path.join(process.cwd(), "components", "Navbar.tsx"), "utf-8");
  const appNavContent = fs.readFileSync(path.join(process.cwd(), "components", "AppNav.tsx"), "utf-8");
  const settingsContent = fs.readFileSync(path.join(process.cwd(), "app", "profile", "settings", "page.tsx"), "utf-8");

  assert.ok(navContent.includes("<ThemeToggle"), "Landing Navbar must include ThemeToggle");
  assert.ok(appNavContent.includes("<ThemeToggle"), "AppNav must include ThemeToggle");
  assert.ok(settingsContent.includes("theme-settings-section"), "Settings must have theme settings section");
  assert.ok(settingsContent.includes("theme-option-light"), "Settings must have Light mode option");
  assert.ok(settingsContent.includes("theme-option-dark"), "Settings must have Dark mode option");
  assert.ok(settingsContent.includes("theme-option-system"), "Settings must have System mode option");
});

test("Component States - Download page renders Available vs Coming Soon correctly", () => {
  const downloadPath = path.join(process.cwd(), "app", "download", "page.tsx");
  const content = fs.readFileSync(downloadPath, "utf-8");

  assert.ok(content.includes("android-status-badge"), "Download page must render status badge");
  assert.ok(content.includes("android-download-button"), "Download page must render download button");
  assert.ok(content.includes("Google Play Protect"), "Download page must provide Google Play Protect guidance");
  assert.ok(content.includes("Apple iOS"), "Download page must preserve iOS stub");
});
