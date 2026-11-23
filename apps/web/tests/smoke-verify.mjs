import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("Landing Page Content & Tokens Smoke Verification", async (t) => {
  // 1. Verify all copy lives in content/landing.ts
  const contentPath = path.resolve("content/landing.ts");
  assert.ok(fs.existsSync(contentPath), "content/landing.ts must exist");
  const contentSource = fs.readFileSync(contentPath, "utf-8");

  // Verify mandatory sections & disclaimer
  assert.ok(
    contentSource.includes("Float provides indicative information only"),
    "Mandatory legal disclaimer must be present in content/landing.ts"
  );
  assert.ok(
    contentSource.includes("Plan your money"),
    "Hero headline must be present in content/landing.ts"
  );
  assert.ok(
    contentSource.includes("Three Pillars"),
    "Three Pillars must be present in content/landing.ts"
  );
  assert.ok(
    contentSource.includes("How Float works"),
    "How it works must be present in content/landing.ts"
  );
  assert.ok(
    contentSource.includes("Try the scam check right now"),
    "Scam demo copy must be present in content/landing.ts"
  );

  // 2. Verify Logo component exists and has data-testid="logo-placeholder"
  const logoPath = path.resolve("components/Logo.tsx");
  assert.ok(fs.existsSync(logoPath), "Logo.tsx component must exist");
  const logoSource = fs.readFileSync(logoPath, "utf-8");
  assert.ok(
    logoSource.includes('data-testid="logo-placeholder"'),
    "Logo component must render marked placeholder"
  );

  // 3. Verify design notes & credits documentation
  assert.ok(
    fs.existsSync("../../docs/web/design-notes.md"),
    "docs/web/design-notes.md must exist"
  );
  assert.ok(
    fs.existsSync("../../docs/web/credits.md"),
    "docs/web/credits.md must exist"
  );

  // 4. Verify API route implementation exists and handles loading, error, 503
  const apiRoutePath = path.resolve("app/api/v1/protect/check/route.ts");
  assert.ok(fs.existsSync(apiRoutePath), "API route must exist at app/api/v1/protect/check/route.ts");
  const apiRouteSource = fs.readFileSync(apiRoutePath, "utf-8");
  assert.ok(
    apiRouteSource.includes("503"),
    "API route must handle 503 status code"
  );
  assert.ok(
    apiRouteSource.includes("POST"),
    "API route must export POST handler"
  );
  assert.ok(
    apiRouteSource.includes("risk_tier"),
    "API route must return risk_tier"
  );

  // 5. Verify no testimonials, customer logos, or fake ratings in content
  assert.ok(
    !contentSource.toLowerCase().includes("testimonial"),
    "No testimonials should be present"
  );
  assert.ok(
    !contentSource.toLowerCase().includes("rated 5 stars"),
    "No fake ratings should be present"
  );
});
