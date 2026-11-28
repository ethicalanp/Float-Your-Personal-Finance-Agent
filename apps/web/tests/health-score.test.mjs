import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("Health Score - API client, Home UI, and plan.md docs are complete", () => {
  const clientSrc = fs.readFileSync(
    path.join(process.cwd(), "..", "..", "packages", "api-client", "src", "client.ts"),
    "utf-8"
  );
  const homeSrc = fs.readFileSync(path.join(process.cwd(), "app", "home", "page.tsx"), "utf-8");
  const planSkill = fs.readFileSync(path.join(process.cwd(), "..", "..", "docs", "skills", "plan.md"), "utf-8");

  assert.ok(clientSrc.includes("getHealthScore"), "api-client must expose getHealthScore");
  assert.ok(clientSrc.includes("updateHealthInsuranceFlag"), "api-client must expose updateHealthInsuranceFlag");

  assert.ok(homeSrc.includes("health-score-card"), "Home must render health-score-card");
  assert.ok(homeSrc.includes("health-score-components"), "Home must render health-score-components");
  assert.ok(homeSrc.includes("float-path-section"), "Home must render float-path-section");
  assert.ok(homeSrc.includes("Insufficient data"), "Home must render Insufficient data for missing components");
  assert.ok(homeSrc.includes("Why:"), "Home must explain why for each component");
  assert.ok(homeSrc.includes("Best next action"), "Home must highlight Best next action");

  assert.ok(planSkill.includes("Float Health Score"), "docs/skills/plan.md must document Float Health Score");
  assert.ok(planSkill.includes("savings_rate"), "docs/skills/plan.md must document component weights");
});
