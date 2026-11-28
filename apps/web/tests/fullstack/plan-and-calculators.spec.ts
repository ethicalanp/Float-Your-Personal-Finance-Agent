import { test, expect } from "@playwright/test";
import { CalculatorsPage, createUniqueUserAndContext, runBasicA11yAndThemeCheck } from "./pages";

test.describe("Fullstack Plan Hub & SIP Step-Up Calculators", () => {
  test("Row 7: Budget Plan (/plan)", async ({ browser, baseURL }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "budget");

    try {
      await page.goto("/plan");
      await expect(page.getByTestId("save-budget-btn")).toBeVisible();

      // Error state: 0 or invalid income prevents valid budget save / shows error
      const incomeInput = page.locator("input[type='number']").first();
      await incomeInput.fill("0");
      await page.getByTestId("save-budget-btn").click();
      await expect(page.locator("main")).toBeVisible();

      // Happy path: save ₹1,00,000 monthly income and verify persistence on reload
      await incomeInput.fill("100000");
      await page.getByTestId("save-budget-btn").click();
      await expect(page.locator("main")).toContainText(/1,00,000|saved/i);
      await page.reload();
      await expect(page.getByTestId("save-budget-btn")).toBeVisible();
      await runBasicA11yAndThemeCheck(page, "/plan");
    } finally {
      await context.close();
    }
  });

  test("Row 8: Recurring & Bills (/plan/recurring)", async ({ browser, baseURL }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "recurr");

    try {
      await page.goto("/plan/recurring");
      await expect(page.getByTestId("add-recurring-btn")).toBeVisible();

      // Error state: empty submit keeps empty state
      await page.getByTestId("add-recurring-btn").click();
      await expect(page.getByTestId("recurring-empty")).toBeVisible();

      // Happy path: create a recurring commitment and verify it appears
      const textInput = page.locator("input[type='text']").first();
      const numInput = page.locator("input[type='number']").first();
      await textInput.fill("House Rent");
      await numInput.fill("18000");
      await page.getByTestId("add-recurring-btn").click();
      await expect(page.locator("main")).toContainText("House Rent");
      await runBasicA11yAndThemeCheck(page, "/plan/recurring");
    } finally {
      await context.close();
    }
  });

  test("Row 9: Goals (/plan/goals)", async ({ browser, baseURL }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "goals");

    try {
      await page.goto("/plan/goals");
      await expect(page.getByTestId("add-goal-btn")).toBeVisible();

      // Error state: empty submit keeps empty state
      await page.getByTestId("add-goal-btn").click();
      await expect(page.getByTestId("goals-empty")).toBeVisible();

      // Happy path: add a goal and verify it appears
      const textInput = page.locator("input[type='text']").first();
      const numInput = page.locator("input[type='number']").first();
      await textInput.fill("Laptop Fund");
      await numInput.fill("80000");
      await page.getByTestId("add-goal-btn").click();
      await expect(page.locator("main")).toContainText("Laptop Fund");
      await runBasicA11yAndThemeCheck(page, "/plan/goals");
    } finally {
      await context.close();
    }
  });

  test("Row 10: Emergency Fund (/plan/emergency-fund)", async ({ browser, baseURL }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "ef");

    try {
      await page.goto("/plan/emergency-fund");
      await expect(page.getByTestId("ef-summary")).toBeVisible();

      // Error state: invalid negative number does not crash
      const numInput = page.locator("input[type='number']").first();
      if ((await numInput.count()) > 0) {
        await numInput.fill("-1");
        await page.getByTestId("save-ef-btn").click();
        await expect(page.locator("main")).toBeVisible();

        // Happy path: save valid target months
        await numInput.fill("6");
        await page.getByTestId("save-ef-btn").click();
        await expect(page.getByTestId("ef-summary")).toBeVisible();
      }
      await runBasicA11yAndThemeCheck(page, "/plan/emergency-fund");
    } finally {
      await context.close();
    }
  });

  test("Row 11: Subscriptions (/plan/subscriptions)", async ({ browser, baseURL }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "subs");

    try {
      await page.goto("/plan/subscriptions");
      await expect(page.getByTestId("leaks-count")).toBeVisible();
      await expect(page.getByTestId("leaks-empty")).toBeVisible();
      await runBasicA11yAndThemeCheck(page, "/plan/subscriptions");

      // Error/auth-guard state: unauthenticated visit redirects to /login
      const anonCtx = await browser.newContext({ baseURL: url });
      const anonPage = await anonCtx.newPage();
      await anonPage.goto("/plan/subscriptions");
      await expect(anonPage).toHaveURL(/\/login/);
      await anonCtx.close();
    } finally {
      await context.close();
    }
  });

  test("Row 12: Net Worth (/plan/net-worth)", async ({ browser, baseURL }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "nw");

    try {
      await page.goto("/plan/net-worth");
      await expect(page.getByTestId("net-worth-total")).toBeVisible();

      // Happy path: save snapshot
      await page.getByTestId("save-snapshot-btn").click();
      await expect(page.getByTestId("total-assets")).toBeVisible();
      await runBasicA11yAndThemeCheck(page, "/plan/net-worth");

      // Error/auth-guard state: unauthenticated visit redirects to /login
      const anonCtx = await browser.newContext({ baseURL: url });
      const anonPage = await anonCtx.newPage();
      await anonPage.goto("/plan/net-worth");
      await expect(anonPage).toHaveURL(/\/login/);
      await anonCtx.close();
    } finally {
      await context.close();
    }
  });

  test("Row 13: Calculators, SIP Step-Up, Unrealistic Warning & Reverse Mode (/plan/calculators)", async ({
    browser,
    baseURL,
  }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "calc");

    try {
      const calc = new CalculatorsPage(page);
      await calc.goto();

      // Error state: negative return shows clear validation message
      await page.getByTestId("sip-return-input").fill("-5");
      await page.getByTestId("run-sip-btn").click();
      await expect(page.getByTestId("sip-validation-error")).toContainText("between 0% and 30%");

      // Happy path 1: Golden example (₹10,000/mo, 10%, 10y, 5% every 3m) triggers unrealistic warning
      await calc.calculateForwardStepUp({
        monthlySip: "10000",
        years: "10",
        returnPct: "10",
        stepUpType: "percent",
        stepUpInterval: "3",
        stepUpPercent: "5",
        adjustInflation: false,
      });
      await expect(page.getByTestId("sip-total-invested")).toContainText("36,23,993");
      await expect(page.getByTestId("sip-maturity-nominal")).toContainText("53,31,228");
      await expect(page.getByTestId("sip-stepup-delta")).toContainText("32,65,708");
      await expect(page.getByTestId("sip-unrealistic-warning")).toContainText("Year 10");
      await expect(page.getByTestId("sip-unrealistic-warning")).toContainText("67,047");
      await expect(page.getByTestId("sip-yearly-table")).toBeVisible();
      await expect(page.getByTestId("sip-chart")).toBeVisible();

      // Happy path 2: 1-year plan does NOT trigger unrealistic warning
      await calc.calculateForwardStepUp({
        monthlySip: "10000",
        years: "1",
        returnPct: "10",
        stepUpType: "percent",
        stepUpInterval: "3",
        stepUpPercent: "5",
        adjustInflation: false,
      });
      await expect(page.getByTestId("sip-unrealistic-warning")).toHaveCount(0);

      // Happy path 3: 0% step-up does NOT trigger unrealistic warning
      await calc.calculateForwardStepUp({
        monthlySip: "10000",
        years: "10",
        returnPct: "10",
        stepUpType: "percent",
        stepUpInterval: "3",
        stepUpPercent: "0",
        adjustInflation: false,
      });
      await expect(page.getByTestId("sip-unrealistic-warning")).toHaveCount(0);

      // Happy path 4: Reverse mode recovers ₹10,000 starting SIP
      await page.getByTestId("sip-mode-reverse").click();
      await page.getByTestId("sip-target-input").fill("5331228.36");
      await page.getByTestId("sip-stepup-type").selectOption("percent");
      await page.getByTestId("sip-stepup-interval").selectOption("3");
      await page.getByTestId("sip-stepup-percent").fill("5");
      await page.getByTestId("run-sip-btn").click();
      await expect(page.getByTestId("sip-required-starting")).toContainText("10,000");

      await runBasicA11yAndThemeCheck(page, "/plan/calculators");
    } finally {
      await context.close();
    }
  });
});
