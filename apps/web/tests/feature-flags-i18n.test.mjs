import test from "node:test";
import assert from "node:assert/strict";
import { FEATURES, isFeatureEnabled } from "../lib/features.ts";
import { getTranslation } from "../lib/i18n.ts";

test("Feature Flags - planned features remain inactive", () => {
  assert.equal(isFeatureEnabled("PLAN_STATEMENT_UPLOAD"), true);
  assert.equal(isFeatureEnabled("PLAN_CASH_FLOW"), true);
  assert.equal(isFeatureEnabled("PROTECT_SCAM_CHECK"), true);
  assert.equal(isFeatureEnabled("BORROW_READINESS_ASSESS"), true);
  assert.equal(isFeatureEnabled("ASSISTANT_KNOWLEDGE_RAG"), true);

  // Planned features without endpoints must be false
  assert.equal(isFeatureEnabled("HEALTH_SCORE_CALCULATOR"), false);
  assert.equal(isFeatureEnabled("BUDGETING_LIMITS"), false);
  assert.equal(isFeatureEnabled("FINANCIAL_GOAL_TRACKER"), false);
  assert.equal(isFeatureEnabled("CREDIT_BUREAU_PULL"), false);
});

test("i18n - English dictionary completeness and fallbacks", () => {
  const en = getTranslation("en");
  assert.ok(en.nav.home);
  assert.ok(en.nav.protect);
  assert.ok(en.nav.borrow);
  assert.ok(en.nav.assistant);
  assert.ok(en.nav.settings);
  assert.ok(en.common.helpline1930.includes("1930"));

  // Fallback for unknown language code
  const fallback = getTranslation("unknown");
  assert.equal(fallback.nav.home, "Home");
});
