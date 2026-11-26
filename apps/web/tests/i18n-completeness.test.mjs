import test from "node:test";
import assert from "node:assert/strict";
import {
  DICTIONARY,
  I18N_METADATA,
  getTranslation,
  formatINR,
  formatISTDate,
} from "../lib/i18n.ts";

function getDeepKeys(obj, prefix = "") {
  let keys = [];
  for (const [k, v] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      keys = keys.concat(getDeepKeys(v, fullKey));
    } else {
      keys.push(fullKey);
    }
  }
  return keys;
}

test("i18n - Completeness: All English keys must exist in Malayalam and Manglish", () => {
  const enKeys = getDeepKeys(DICTIONARY.en);
  const mlKeys = new Set(getDeepKeys(DICTIONARY.ml));
  const manglishKeys = new Set(getDeepKeys(DICTIONARY.manglish));

  const missingInMl = enKeys.filter((k) => !mlKeys.has(k));
  const missingInManglish = enKeys.filter((k) => !manglishKeys.has(k));

  assert.deepEqual(
    missingInMl,
    [],
    `Missing Malayalam translation keys: ${missingInMl.join(", ")}`
  );
  assert.deepEqual(
    missingInManglish,
    [],
    `Missing Manglish translation keys: ${missingInManglish.join(", ")}`
  );
});

test("i18n - Metadata: Malayalam and Manglish are marked needsReview and NOT verified", () => {
  assert.equal(I18N_METADATA.en.verified, true);
  assert.equal(I18N_METADATA.en.needsReview, false);

  assert.equal(I18N_METADATA.ml.needsReview, true);
  assert.equal(I18N_METADATA.ml.verified, false);

  assert.equal(I18N_METADATA.manglish.needsReview, true);
  assert.equal(I18N_METADATA.manglish.verified, false);
});

test("i18n - Fallback: Unknown or missing language defaults to English", () => {
  const fallback = getTranslation("es"); // Spanish not present
  assert.equal(fallback.nav.home, "Home");
  assert.equal(fallback.common.retry, "Retry");
});

test("i18n - INR Currency Formatting: Standard, compact Lakh/Crore, and privacy masking", () => {
  // Standard format
  const standard = formatINR(150000);
  assert.ok(standard.includes("1,50,000"));

  // Compact Lakh format
  const lakh = formatINR(250000, { compact: true });
  assert.equal(lakh, "₹ 2.50 L");

  // Compact Crore format
  const crore = formatINR(35000000, { compact: true });
  assert.equal(crore, "₹ 3.50 Cr");

  // Privacy masked mode
  const masked = formatINR(540000, { hideAmount: true });
  assert.equal(masked, "₹ ••••••");
});

test("i18n - IST Date Formatting: Enforces Asia/Kolkata timezone", () => {
  // 2026-11-25T12:00:00Z is 17:30 IST on the same day
  const utcDate = "2026-11-25T12:00:00Z";
  const formatted = formatISTDate(utcDate, "medium");
  assert.ok(formatted.includes("2026"));
  assert.ok(formatted.includes("Nov"));

  const fullFormatted = formatISTDate(utcDate, "full");
  assert.ok(fullFormatted.includes("5:30") || fullFormatted.includes("17:30"));
});
