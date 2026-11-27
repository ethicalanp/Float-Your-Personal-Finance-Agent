import { test, expect } from "@playwright/test";

test.describe("Float MVP End-to-End User Flow (Mocked & Themed)", () => {
  test.beforeEach(async ({ page }) => {
    (page as any).__cspViolations = [];
    page.on("console", (msg) => {
      const text = msg.text();
      if (
        msg.type() === "error" &&
        (text.toLowerCase().includes("content security policy") ||
          text.toLowerCase().includes("content-security-policy") ||
          text.toLowerCase().includes("violates the following"))
      ) {
        (page as any).__cspViolations.push(`Console CSP Error: ${text}`);
      }
    });

    await page.addInitScript(() => {
      window.addEventListener("securitypolicyviolation", (e: SecurityPolicyViolationEvent) => {
        (window as any).__securityPolicyViolations = (window as any).__securityPolicyViolations || [];
        (window as any).__securityPolicyViolations.push({
          blockedURI: e.blockedURI,
          violatedDirective: e.violatedDirective,
          effectiveDirective: e.effectiveDirective,
        });
      });
    });

    // Mock Backend Endpoints (strictly scoped to /api/ to never intercept _next/ static bundles)
    await page.route("**/api/auth/capabilities*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ google: false, phone: true, email: true }),
      })
    );

    await page.route("**/api/auth/register*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          user: { id: "mock-user-1", email: "playwright@example.com", full_name: "Playwright Tester" },
        }),
      })
    );

    await page.route("**/api/auth/me*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          user_id: "mock-user-1",
          consent: { ai_data_processing_consent: true, terms_accepted: true },
        }),
      })
    );

    await page.route("**/api/backend/**/plan/accounts*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "acc-101",
            name: "Primary Savings",
            account_type: "savings",
            institution_name: "HDFC Bank",
            account_number_mask: "****1234",
            currency: "INR",
            current_balance: 75000,
            created_at: "2026-01-01T00:00:00Z",
          },
        ]),
      })
    );

    await page.route("**/api/backend/**/plan/cash-flow*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total_inflow: 90000,
          total_outflow: 40000,
          net_savings: 50000,
          top_categories: [{ category: "Rent", total_amount: 25000, count: 1 }],
          monthly_breakdown: [{ month: "2026-11", inflow: 90000, outflow: 40000, net: 50000 }],
        }),
      })
    );

    await page.route("**/api/backend/**/plan/health-score*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          formula_version: "v1.0.0",
          month: "2026-11",
          overall_score: 78,
          band: "steady",
          confidence: "medium",
          available_components: 4,
          total_components: 6,
          has_essential_insurance: null,
          components: [
            {
              key: "savings_rate",
              label: "Savings Rate",
              status: "available",
              score: 100,
              weight: 25,
              value_display: "55.6%",
              why: "Net cash flow this month is 55.6% of monthly income.",
              educational_tip: "Aiming to retain 20% or more builds resilience.",
            },
            {
              key: "insurance_flag",
              label: "Essential Insurance",
              status: "insufficient_data",
              score: null,
              weight: 10,
              value_display: "Insufficient data",
              why: "Self-reported insurance status has not been set yet.",
              educational_tip: "Set your essential insurance status below.",
            },
          ],
          best_next_action: {
            priority: 1,
            pillar: "Protect",
            title: "Confirm essential protection status",
            why: "Verifying health/term coverage helps guard against unexpected medical expenses.",
            href: "/home#health-score",
          },
          float_path: [
            {
              priority: 1,
              pillar: "Protect",
              title: "Confirm essential protection status",
              why: "Verifying health/term coverage helps guard against unexpected medical expenses.",
              href: "/home#health-score",
            },
          ],
          history: [],
          delta_from_previous: null,
          version_changed: false,
          disclaimer: "Educational financial health indicator only.",
        }),
      })
    );

    await page.route("**/api/backend/**/plan/upload-statement*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          account_id: "acc-101",
          total_parsed: 15,
          imported_count: 15,
          duplicates_skipped: 0,
          sample_imported: [],
        }),
      })
    );

    await page.route("**/api/backend/**/protect/check*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "success",
          analysis: {
            is_scam: true,
            risk_tier: "HIGH",
            risk_score: 88,
            detected_patterns: ["ELECTRICITY_DISCONNECTION_SCAM"],
            reasons: ["Threat of urgent power cut", "Unverified APK/bitly link"],
            recommendations: ["Do not call unverified numbers", "Report immediately to 1930"],
            helpline_contact: "1930",
          },
        }),
      })
    );

    await page.route("**/api/backend/**/borrow/assess*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          assessment_id: "assess-001",
          readiness_band: "Tier 1 - Strong",
          readiness_score: 0.85,
          summary: "Excellent cash flow stability",
          positive_factors: ["Consistent monthly inflow", "Low outflow ratio"],
          areas_for_improvement: [],
          recommended_actions: [],
          legal_disclaimer: "Indicative readiness only. Float is not a lender or credit rating agency.",
          assessed_at: "2026-11-25T12:00:00Z",
        }),
      })
    );

    await page.route("**/api/backend/**/assistant/conversations*", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );

    await page.route("**/api/backend/**/assistant/chat/stream", (route) =>
      route.fulfill({
        status: 501,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "STREAMING_DISABLED" } }),
      })
    );

    await page.route("**/api/backend/**/assistant/chat", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "success",
          answer: "Under RBI guidelines, report unauthorized transactions within 3 days for zero liability.",
          citations: [
            {
              chunk_id: "chunk-rbi-1",
              source_title: "RBI Zero Liability Circular 2017",
              source_url: "https://rbi.org.in",
            },
          ],
          confidence: "high",
          disclaimer: "Official regulatory citation.",
        }),
      })
    );
  });

  test.afterEach(async ({ page }) => {
    const windowViolations = await page.evaluate(() => (window as any).__securityPolicyViolations || []);
    const consoleViolations = (page as any).__cspViolations || [];
    expect(windowViolations, `SecurityPolicyViolation: ${JSON.stringify(windowViolations)}`).toHaveLength(0);
    expect(consoleViolations, `Console CSP errors: ${consoleViolations.join("; ")}`).toHaveLength(0);
  });

  for (const theme of ["light", "dark"] as const) {
    test(`full e2e walkthrough in ${theme} theme: signup -> home -> protect -> borrow -> assistant`, async ({
      page,
      context,
    }) => {
      // 1. Visit signup page and apply theme
      await page.goto("/signup");
      await page.evaluate((t) => {
        document.documentElement.setAttribute("data-scheme", t);
        if (t === "dark") document.documentElement.classList.add("dark");
        else document.documentElement.classList.remove("dark");
      }, theme);

      await expect(page.locator("h1, h2")).toContainText(/create your float account/i);

      // Now set mock auth cookie for protected screens
      await context.addCookies([
        {
          name: "float_token",
          value: "mock-jwt-test-token",
          domain: "127.0.0.1",
          path: "/",
          httpOnly: true,
          sameSite: "Lax",
        },
      ]);

      // 2. Navigate to Home & Verify Cash Flow + Health Score
      await page.goto("/home");
      await expect(page.locator("h1")).toContainText("Financial Overview");
      await expect(page.locator("text=Total Inflow")).toBeVisible({ timeout: 10000 });
      await expect(page.locator("text=Total Outflow")).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="health-score-card"]')).toBeVisible();
      await expect(page.locator('[data-testid="health-score-value"]')).toContainText("78/100");
      await expect(page.locator('[data-testid="float-path-section"]')).toBeVisible();

      // 3. Test Protect & Scam Check
      await page.goto("/protect");
      await expect(page.locator("h1")).toContainText("Fraud Defense Center");
      await page.fill(
        "textarea",
        "Your electricity will be disconnected tonight. Call officer at 9876543210."
      );
      await page.click('button:has-text("Analyze Message")');
      await expect(page.locator("text=HIGH RISK")).toBeVisible({ timeout: 10000 });
      await expect(page.locator("text=Identified Red Flags:")).toBeVisible();

      // 4. Test Borrow Readiness
      await page.goto("/borrow");
      await expect(page.locator("h1")).toContainText("Loan & Credit Readiness");
      await page.click('button:has-text("Assess My Readiness")');
      await expect(page.locator("text=Tier 1 - Strong")).toBeVisible();
      await expect(page.locator("text=Indicative readiness only")).toBeVisible();

      // 5. Test Float.ai (/assistant 308 -> /chat)
      await page.goto("/assistant");
      await expect(page).toHaveURL(/\/chat$/);
      await expect(page.locator("h1")).toContainText("Float.ai");
      await page.getByRole("button", { name: /1930 cybercrime helpline|RBI 3-day zero liability/i }).first().click();
      await expect(page.locator("text=RBI Zero Liability Circular")).toBeVisible({ timeout: 10000 });
    });
  }
});
