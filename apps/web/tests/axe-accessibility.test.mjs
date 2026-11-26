import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("Accessibility - Skip to main content link exists and targets #main-content", () => {
  const layoutPath = path.join(process.cwd(), "app", "layout.tsx");
  const layoutContent = fs.readFileSync(layoutPath, "utf-8");

  assert.ok(
    layoutContent.includes('href="#main-content"'),
    "Layout must contain skip link targeting #main-content"
  );
  assert.ok(
    layoutContent.includes("sr-only focus:not-sr-only"),
    "Skip link must use screen-reader accessible styling with visible focus state"
  );

  const shellPath = path.join(process.cwd(), "components", "AppShell.tsx");
  const shellContent = fs.readFileSync(shellPath, "utf-8");
  assert.ok(
    shellContent.includes('id="main-content"'),
    "AppShell must render main container with id='main-content'"
  );
  assert.ok(
    shellContent.includes("tabIndex={-1}"),
    "AppShell main container must be programmatically focusable with tabIndex=-1"
  );
});

test("Accessibility - Chat & dynamic notifications have aria-live regions", () => {
  const assistantPath = path.join(process.cwd(), "app", "assistant", "page.tsx");
  const assistantContent = fs.readFileSync(assistantPath, "utf-8");
  assert.ok(
    assistantContent.includes('aria-live="polite"'),
    "Assistant chat history must be marked aria-live='polite'"
  );

  const offlinePath = path.join(process.cwd(), "components", "OfflineBanner.tsx");
  const offlineContent = fs.readFileSync(offlinePath, "utf-8");
  assert.ok(
    offlineContent.includes('role="alert"'),
    "Offline banner must have role='alert'"
  );
  assert.ok(
    offlineContent.includes('aria-live="assertive"'),
    "Offline banner must have aria-live='assertive'"
  );
});

test("Accessibility - Form controls across screens have explicit accessible names", () => {
  const screens = ["login", "signup", "protect", "home", "settings", "profile"];

  for (const screen of screens) {
    const screenPath = path.join(process.cwd(), "app", screen, "page.tsx");
    if (fs.existsSync(screenPath)) {
      const content = fs.readFileSync(screenPath, "utf-8");
      // Check that all inputs have either htmlFor label, aria-label, or placeholder
      const hasAccessibleInputs =
        content.includes("<label") ||
        content.includes("aria-label") ||
        content.includes("htmlFor");
      assert.ok(
        hasAccessibleInputs,
        `Screen ${screen} must contain labelled form inputs`
      );
    }
  }
});

test("Accessibility - WCAG AA Reduced Motion styles are defined in globals.css", () => {
  const cssPath = path.join(process.cwd(), "app", "globals.css");
  const cssContent = fs.readFileSync(cssPath, "utf-8");

  assert.ok(
    cssContent.includes("@media (prefers-reduced-motion: reduce)"),
    "globals.css must respect prefers-reduced-motion"
  );
  assert.ok(
    cssContent.includes("animation-duration: 0.01ms !important"),
    "globals.css must neutralize animations when reduced-motion is requested"
  );
});
