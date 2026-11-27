import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("Plan & Recurring pages - exist in AppNav, middleware, and support required UI states", () => {
  const navSrc = fs.readFileSync(path.join(process.cwd(), "components", "AppNav.tsx"), "utf-8");
  const mwSrc = fs.readFileSync(path.join(process.cwd(), "middleware.ts"), "utf-8");
  const planSrc = fs.readFileSync(path.join(process.cwd(), "app", "plan", "page.tsx"), "utf-8");
  const recSrc = fs.readFileSync(path.join(process.cwd(), "app", "recurring", "page.tsx"), "utf-8");

  assert.ok(navSrc.includes('href: "/plan"'), "AppNav must link to /plan");
  assert.ok(navSrc.includes('href: "/recurring"'), "AppNav must link to /recurring");
  assert.ok(mwSrc.includes('"/plan"') && mwSrc.includes('"/recurring"'), "middleware.ts must protect /plan and /recurring");

  // Plan required states & controls
  assert.ok(planSrc.includes("plan-skeleton"), "Plan must render loading skeleton");
  assert.ok(planSrc.includes('role="alert"'), "Plan must render error alert");
  assert.ok(planSrc.includes("unallocated-indicator"), "Plan must render unallocated indicator");
  assert.ok(planSrc.includes("basePaise <= 0"), "Plan must reject zero or negative income");
  assert.ok(planSrc.includes("Math.abs(unallocatedPct) > 0.01"), "Plan must disable save when percentages != 100%");
  assert.ok(planSrc.includes("expected_version"), "Plan must send expected_version for optimistic concurrency");
  assert.ok(planSrc.includes("isSubmitting.current"), "Plan must guard against double submit");
  assert.ok(planSrc.includes("hideAmounts"), "Plan must respect hideAmounts privacy toggle");

  // Recurring required states & controls
  assert.ok(recSrc.includes("recurring-skeleton"), "Recurring must render loading skeleton");
  assert.ok(recSrc.includes("due-soon-strip"), "Recurring must render due-soon strip");
  assert.ok(recSrc.includes("candidates-inbox"), "Recurring must render candidates inbox");
  assert.ok(recSrc.includes("isSubmitting.current"), "Recurring must guard against double submit");
  assert.ok(recSrc.includes("hideAmounts"), "Recurring must respect hideAmounts privacy toggle");
});
