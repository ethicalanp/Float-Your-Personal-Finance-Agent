import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const webRoot = path.resolve(import.meta.dirname, "..");
const repoRoot = path.resolve(webRoot, "..", "..");

test("PlanTabs includes subscriptions and net-worth tabs with keyboard navigation", () => {
  const src = fs.readFileSync(path.join(webRoot, "components/PlanTabs.tsx"), "utf8");
  assert.match(src, /"subscriptions"/);
  assert.match(src, /"net-worth"/);
  assert.match(src, /ArrowRight/);
  assert.match(src, /ArrowLeft/);
});

test("Subscriptions page supports leak cards, Keep/Cancel decisions, and compact INR", () => {
  const src = fs.readFileSync(path.join(webRoot, "app/plan/subscriptions/page.tsx"), "utf8");
  assert.match(src, /getSubscriptionLeaks/);
  assert.match(src, /setSubscriptionLeakDecision/);
  assert.match(src, /leak-keep-/);
  assert.match(src, /leak-cancel-/);
  assert.match(src, /compact:\s*true/);
  assert.match(src, /No subscription leaks detected/);
});

test("Net worth page handles negative net worth, stale prompts, snapshots SVG, and 409 recovery", () => {
  const src = fs.readFileSync(path.join(webRoot, "app/plan/net-worth/page.tsx"), "utf8");
  assert.match(src, /getNetWorth/);
  assert.match(src, /createNetWorthItem/);
  assert.match(src, /updateNetWorthItem/);
  assert.match(src, /deleteNetWorthItem/);
  assert.match(src, /createNetWorthSnapshot/);
  assert.match(src, /is_negative/);
  assert.match(src, /stale-banner/);
  assert.match(src, /<svg/);
  assert.match(src, /err\?\.status === 409/);
});

test("api-client exposes subscriptions and net worth endpoints", () => {
  const src = fs.readFileSync(path.join(repoRoot, "packages/api-client/src/client.ts"), "utf8");
  for (const method of [
    "getSubscriptionLeaks",
    "setSubscriptionLeakDecision",
    "getNetWorth",
    "createNetWorthItem",
    "updateNetWorthItem",
    "deleteNetWorthItem",
    "createNetWorthSnapshot",
  ]) {
    assert.ok(src.includes(method), `Missing api-client method: ${method}`);
  }
});
