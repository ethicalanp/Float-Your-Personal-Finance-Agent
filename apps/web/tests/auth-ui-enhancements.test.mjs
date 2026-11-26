import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("Auth UI - Google on login and signup is driven by capabilities flag", () => {
  const loginSrc = fs.readFileSync(path.join(process.cwd(), "app", "login", "page.tsx"), "utf-8");
  const signupSrc = fs.readFileSync(path.join(process.cwd(), "app", "signup", "page.tsx"), "utf-8");

  // Google button is wrapped in capabilities.google check
  assert.ok(loginSrc.includes("capabilities.google &&"), "Login must gate Google on capabilities.google");
  assert.ok(signupSrc.includes("capabilities.google &&"), "Signup must gate Google on capabilities.google");

  // Uses GoogleSignInButton with visible GIS renderButton
  assert.ok(loginSrc.includes("GoogleSignInButton"), "Login must render GoogleSignInButton");
  assert.ok(signupSrc.includes("GoogleSignInButton"), "Signup must render GoogleSignInButton");
  assert.ok(!loginSrc.includes("__MOCK_GOOGLE_ID_TOKEN__"), "Login must not contain debug mock token hook");
  assert.ok(!signupSrc.includes("__MOCK_GOOGLE_ID_TOKEN__"), "Signup must not contain debug mock token hook");

  // Handles failure gracefully without crash
  assert.ok(loginSrc.includes("Google sign-in was unsuccessful"), "Login must contain user-friendly Google error handling");
});

test("Auth UI - Warped concave/pincushion FLOAT background is CSP-safe and accessible", () => {
  const bgSrc = fs.readFileSync(path.join(process.cwd(), "components", "WarpedFloatBackground.tsx"), "utf-8");

  // Accessibility: aria-hidden="true" and pointer-events-none
  assert.ok(bgSrc.includes('aria-hidden="true"'), "Decorative background must be aria-hidden");
  assert.ok(bgSrc.includes("pointer-events-none"), "Decorative background must not intercept pointer events");

  // SVG per-letter transformation for F, L, O, A, T
  assert.ok(/>F\r?\n|\sF\r?\n|>F</.test(bgSrc), "Must contain letter F");
  assert.ok(/>L\r?\n|\sL\r?\n|>L</.test(bgSrc), "Must contain letter L");
  assert.ok(/>O\r?\n|\sO\r?\n|>O</.test(bgSrc), "Must contain letter O");
  assert.ok(/>A\r?\n|\sA\r?\n|>A</.test(bgSrc), "Must contain letter A");
  assert.ok(/>T\r?\n|\sT\r?\n|>T</.test(bgSrc), "Must contain letter T");
  assert.ok(bgSrc.includes("scale(1.18, 1.45)"), "Outer letters must flare tall and outward");
  assert.ok(bgSrc.includes("scale(0.92, 0.85)") || bgSrc.includes("scale(0.9"), "Middle letter must pinch inward");

  // Parallax: fine pointer check & prefers-reduced-motion check
  assert.ok(bgSrc.includes("(pointer: fine)"), "Parallax must only activate for fine pointer");
  assert.ok(bgSrc.includes("(prefers-reduced-motion: reduce)"), "Parallax must respect reduced motion");
  assert.ok(!bgSrc.includes("<script"), "Decorative layer must be CSP-safe with zero inline scripts");
});

test("Get App Prompt - Route exclusions, session limits, and dismissal retention", () => {
  const promptSrc = fs.readFileSync(path.join(process.cwd(), "components", "GetAppPrompt.tsx"), "utf-8");

  // Excluded routes check
  const expectedExcluded = ["/download", "/login", "/signup", "/terms", "/privacy", "/security"];
  for (const route of expectedExcluded) {
    assert.ok(promptSrc.includes(route), `Excluded routes must include ${route}`);
  }

  // Session limits and 14-day localStorage check
  assert.ok(promptSrc.includes("float_get_app_session_shown"), "Prompt must track session display");
  assert.ok(promptSrc.includes("float_get_app_dismissed_until"), "Prompt must track 14-day dismissal");
  assert.ok(promptSrc.includes("14 * 24 * 60 * 60 * 1000"), "Must compute 14-day duration in milliseconds");

  // Keyboard accessibility & reduced motion
  assert.ok(promptSrc.includes('e.key === "Escape"'), "Escape key must dismiss the prompt");
  assert.ok(promptSrc.includes("motion-reduce:transition-none"), "Prompt must respect reduced motion");

  // Platform handling: Android APK or coming soon, iOS coming soon
  assert.ok(promptSrc.includes("Android: Coming soon"), "Must handle Android coming soon state");
  assert.ok(promptSrc.includes("iOS: Coming soon"), "Must handle iOS coming soon state");
});

test("SocialButton - Demo renders Google, Apple, and Phone without GitHub", () => {
  const demoSrc = fs.readFileSync(path.join(process.cwd(), "components", "ui", "demo.tsx"), "utf-8");

  assert.ok(demoSrc.includes('brand="google"'), "Demo must include Google");
  assert.ok(demoSrc.includes('brand="apple"'), "Demo must include Apple");
  assert.ok(demoSrc.includes('brand="custom"'), "Demo must include Phone via brand=custom");
  assert.ok(demoSrc.includes("Phone"), "Demo must label custom button as Phone");
  assert.ok(!demoSrc.includes('brand="github"'), "Demo must NOT include GitHub");
});

test("Settings - Sign-in methods and active sessions support full lifecycle", () => {
  const settingsSrc = fs.readFileSync(path.join(process.cwd(), "app", "settings", "page.tsx"), "utf-8");

  // Last method removal protection
  assert.ok(settingsSrc.includes("isSoleMethod") || settingsSrc.includes("totalMethodsCount <= 1"), "Must prevent unlinking sole method");
  assert.ok(settingsSrc.includes("handleUnlinkMethod"), "Must support unlinking methods");
  assert.ok(settingsSrc.includes("handleRevokeSession"), "Must support revoking sessions");
  assert.ok(settingsSrc.includes("handleLogoutAll"), "Must support logout-all");
});
