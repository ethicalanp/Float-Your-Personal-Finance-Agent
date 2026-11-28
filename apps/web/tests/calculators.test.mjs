import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const webRoot = path.resolve(import.meta.dirname, "..");
const repoRoot = path.resolve(webRoot, "..", "..");

test("PlanTabs includes calculators tab with keyboard navigation", () => {
  const src = fs.readFileSync(path.join(webRoot, "components/PlanTabs.tsx"), "utf8");
  assert.match(src, /"calculators"/);
  assert.match(src, /ArrowRight/);
});

test("Calculators page renders SIP, insurance gap, tax comparison, and educational disclaimers", () => {
  const src = fs.readFileSync(path.join(webRoot, "app/plan/calculators/page.tsx"), "utf8");
  assert.match(src, /calculateSip/);
  assert.match(src, /calculateInsuranceGap/);
  assert.match(src, /compareTaxRegimes/);
  assert.match(src, /Adjust for inflation/);
  assert.match(src, /educational_notice/);
  assert.match(src, /source_url/);
  assert.match(src, /sip-mode-reverse/);
  assert.match(src, /sip-stepup-type/);
  assert.match(src, /sip-yearly-table/);
  assert.match(src, /sip-chart/);
  assert.match(src, /sip-convention/);
});

test("api-client exposes calculator endpoints", () => {
  const src = fs.readFileSync(path.join(repoRoot, "packages/api-client/src/client.ts"), "utf8");
  for (const method of ["calculateSip", "calculateInsuranceGap", "compareTaxRegimes"]) {
    assert.ok(src.includes(method), `Missing api-client method: ${method}`);
  }
});
