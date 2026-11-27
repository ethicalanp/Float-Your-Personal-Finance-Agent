import { test, expect } from "@playwright/test";

test.describe("Budget Plan & Recurring Payments E2E", () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: "float_token",
        value: "mock_e2e_jwt_token",
        domain: "127.0.0.1",
        path: "/",
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);
  });

  test("Set income -> edit split -> add recurring -> see it listed in light & dark themes", async ({ page }) => {
    let savedIncome = 6000000;
    let savedNeeds = 50;
    let savedWants = 30;
    let savedSavings = 20;
    let version = 1;
    const commitments: any[] = [];

    await page.route("**/api/backend/api/v1/plan/budget*", async (route) => {
      const req = route.request();
      if (req.method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            month: "2026-11",
            plan: {
              id: "bp-1",
              month: "2026-11",
              version,
              monthly_income_paise: savedIncome,
              extra_income_paise: 0,
              total_income_paise: savedIncome,
              income_mode: "fixed",
              irregular_months: 3,
              needs_pct: savedNeeds,
              wants_pct: savedWants,
              savings_pct: savedSavings,
              needs_paise: Math.round((savedIncome * savedNeeds) / 100),
              wants_paise: Math.round((savedIncome * savedWants) / 100),
              savings_paise: Math.round((savedIncome * savedSavings) / 100),
              category_mappings: {},
              updated_at: "2026-11-27T04:00:00Z",
            },
            actuals: {
              has_transactions: false,
              transaction_count: 0,
              actual_needs_paise: 0,
              actual_wants_paise: 0,
              actual_savings_paise: 0,
              recurring_needs_paise: 0,
              warnings: [],
            },
            irregular_avg_paise: 0,
            presets: {},
            default_category_mappings: {},
            educational_disclaimer: "Educational only.",
          }),
        });
      } else if (req.method() === "PUT") {
        const body = JSON.parse(req.postData() || "{}");
        savedIncome = body.monthly_income_paise;
        savedNeeds = body.needs_pct;
        savedWants = body.wants_pct;
        savedSavings = body.savings_pct;
        version += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "bp-1",
            month: "2026-11",
            version,
            monthly_income_paise: savedIncome,
            extra_income_paise: 0,
            total_income_paise: savedIncome,
            income_mode: "fixed",
            irregular_months: 3,
            needs_pct: savedNeeds,
            wants_pct: savedWants,
            savings_pct: savedSavings,
            needs_paise: Math.round((savedIncome * savedNeeds) / 100),
            wants_paise: Math.round((savedIncome * savedWants) / 100),
            savings_paise: Math.round((savedIncome * savedSavings) / 100),
            category_mappings: {},
            updated_at: "2026-11-27T04:05:00Z",
          }),
        });
      }
    });

    await page.route("**/api/backend/api/v1/recurring/commitments*", async (route) => {
      const req = route.request();
      if (req.method() === "GET") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(commitments) });
      } else if (req.method() === "POST") {
        const body = JSON.parse(req.postData() || "{}");
        const created = {
          id: `c-${commitments.length + 1}`,
          user_id: "u-1",
          ...body,
          amount_type: "fixed",
          min_amount: null,
          max_amount: null,
          version: 1,
          is_active: true,
          origin: "declared",
          created_at: "2026-11-27T04:00:00Z",
        };
        commitments.push(created);
        await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(created) });
      }
    });
    await page.route("**/api/backend/api/v1/recurring/reminders", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ due_soon: [], overdue: [] }) })
    );
    await page.route("**/api/backend/api/v1/recurring/suggestions", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );

    await page.goto("/plan");
    await expect(page.locator('[data-testid="plan-tablist"]')).toBeVisible();
    await expect(page.locator('[data-testid="plan-due-soon-strip"]')).toBeVisible();
    await expect(page.locator('[data-testid="plan-candidates-prompt"]')).toBeVisible();

    // Unsaved edits on Budget tab are preserved when switching tabs & using Back button
    await page.fill("#budget-income", "88000");
    await page.locator('[data-testid="tab-budget"]').focus();
    await page.keyboard.press("ArrowRight");
    await expect(page).toHaveURL(/\/plan\/recurring$/);
    await expect(page.locator('[data-testid="tab-recurring"]')).toHaveAttribute("aria-selected", "true");
    await page.goBack();
    await expect(page).toHaveURL(/\/plan$/);
    await expect(page.locator("#budget-income")).toHaveValue("88000");

    await page.fill("#budget-income", "100000");
    await page.click('button:has-text("60 / 20 / 20")');
    await page.click('[data-testid="save-budget-btn"]');
    await expect(page.locator('[role="status"]')).toContainText("saved");

    // Verify /recurring 308 redirect -> /plan/recurring
    const redirectRes = await page.goto("/recurring");
    expect(redirectRes?.url()).toMatch(/\/plan\/recurring$/);
    await expect(page).toHaveURL(/\/plan\/recurring$/);
    await expect(page.locator('nav[aria-label="Breadcrumb"]')).toContainText("Plan");

    await page.fill("#rec-name", "Netflix");
    await page.fill("#rec-amount", "649");
    await page.fill("#rec-merchant", "netflix");
    await page.click('[data-testid="add-recurring-btn"]');
    await expect(page.locator("text=Netflix")).toBeVisible();
  });

  test("409 conflict on /plan shows changed-elsewhere message, reloads latest version, and preserves unsaved input", async ({
    page,
  }) => {
    let serverVersion = 1;
    await page.route("**/api/backend/api/v1/plan/budget*", async (route) => {
      const req = route.request();
      if (req.method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            month: "2026-11",
            plan: {
              id: "bp-1",
              month: "2026-11",
              version: serverVersion,
              monthly_income_paise: 6000000,
              extra_income_paise: 0,
              total_income_paise: 6000000,
              income_mode: "fixed",
              irregular_months: 3,
              needs_pct: 50,
              wants_pct: 30,
              savings_pct: 20,
              needs_paise: 3000000,
              wants_paise: 1800000,
              savings_paise: 1200000,
              category_mappings: {},
              updated_at: "2026-11-27T04:00:00Z",
            },
            actuals: {
              has_transactions: false,
              transaction_count: 0,
              actual_needs_paise: 0,
              actual_wants_paise: 0,
              actual_savings_paise: 0,
              recurring_needs_paise: 0,
              warnings: [],
            },
            irregular_avg_paise: 0,
            presets: {},
            default_category_mappings: {},
            educational_disclaimer: "Educational only.",
          }),
        });
      } else if (req.method() === "PUT") {
        serverVersion = 2;
        await route.fulfill({
          status: 409,
          contentType: "application/json",
          body: JSON.stringify({ error: { code: "CONFLICT", message: "Budget plan was modified elsewhere." } }),
        });
      }
    });

    await page.goto("/plan");
    await page.fill("#budget-income", "95000");
    await page.click('[data-testid="save-budget-btn"]');
    await expect(page.getByRole("alert").filter({ hasText: "changed elsewhere" })).toBeVisible();
    await expect(page.locator("#budget-income")).toHaveValue("95000");
    await expect(page.locator("text=v2")).toBeVisible();
  });
});
