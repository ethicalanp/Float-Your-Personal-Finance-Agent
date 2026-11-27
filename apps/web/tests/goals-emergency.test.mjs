import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("Goals & Emergency Fund - routes, PlanSubNav, 409 recovery, and api-client", () => {
  const clientSrc = fs.readFileSync(
    path.join(process.cwd(), "..", "..", "packages", "api-client", "src", "client.ts"),
    "utf-8"
  );
  const subNavSrc = fs.readFileSync(path.join(process.cwd(), "components", "PlanTabs.tsx"), "utf-8");
  const goalsSrc = fs.readFileSync(path.join(process.cwd(), "app", "plan", "goals", "page.tsx"), "utf-8");
  const efSrc = fs.readFileSync(path.join(process.cwd(), "app", "plan", "emergency-fund", "page.tsx"), "utf-8");

  assert.ok(clientSrc.includes("getGoals") && clientSrc.includes("getEmergencyFund"), "api-client must expose goals & emergency fund methods");
  assert.ok(subNavSrc.includes('"/plan/goals"') && subNavSrc.includes('"/plan/emergency-fund"'), "PlanTabs must link to goals and emergency fund");
  assert.ok(goalsSrc.includes("goals-conflict-banner"), "Goals page must show allocation conflict banner");
  assert.ok(goalsSrc.includes("changed elsewhere"), "Goals page must handle 409 conflicts clearly");
  assert.ok(efSrc.includes("changed elsewhere"), "Emergency fund page must handle 409 conflicts clearly");
});
