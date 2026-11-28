import { test, expect } from "@playwright/test";
import { CalculatorsPage, createUniqueUserAndContext, runBasicA11yAndThemeCheck } from "./pages";

test.describe("Fullstack Plan Hub & SIP Step-Up Calculators", () => {
  test("SIP golden example, reverse mode, invalid input, and all plan tabs", async ({
    browser,
    baseURL,
  }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "plancalc");

    try {
      const calc = new CalculatorsPage(page);
      await calc.goto();

      // 1. Invalid input check (negative return)
      await page.getByTestId("sip-return-input").fill("-5");
      await page.getByTestId("run-sip-btn").click();
      await expect(page.getByTestId("sip-validation-error")).toContainText("between 0% and 30%");

      // 2. Golden example: ₹10,000/mo, 10% p.a., 10y, 5% every 3 months
      await calc.calculateForwardStepUp({
        monthlySip: "10000",
        years: "10",
        returnPct: "10",
        stepUpType: "percent",
        stepUpInterval: "3",
        stepUpPercent: "5",
        adjustInflation: false,
      });

      // Assert displayed figures match golden example (₹36,23,993.23 / ₹53,31,228.36)
      await expect(page.getByTestId("sip-total-invested")).toContainText("36,23,993");
      await expect(page.getByTestId("sip-maturity-nominal")).toContainText("53,31,228");
      await expect(page.getByTestId("sip-stepup-delta")).toContainText("32,65,708");
      await expect(page.getByTestId("sip-yearly-table")).toBeVisible();
      await expect(page.getByTestId("sip-chart")).toBeVisible();

      // 3. Reverse mode: target ₹53,31,228.36 -> required starting SIP ~₹10,000
      await page.getByTestId("sip-mode-reverse").click();
      await page.getByTestId("sip-target-input").fill("5331228.36");
      await page.getByTestId("run-sip-btn").click();
      await expect(page.getByTestId("sip-required-starting")).toContainText("10,000");

      await runBasicA11yAndThemeCheck(page, "/plan/calculators");

      // 4. Visit all Plan hub routes (/plan, /plan/recurring, /plan/goals, /plan/emergency-fund, /plan/subscriptions, /plan/net-worth)
      for (const route of [
        "/plan",
        "/plan/recurring",
        "/plan/goals",
        "/plan/emergency-fund",
        "/plan/subscriptions",
        "/plan/net-worth",
      ]) {
        await page.goto(route);
        await expect(page.locator("main")).toBeVisible();
        await runBasicA11yAndThemeCheck(page, route);
      }
    } finally {
      await context.close();
    }
  });
});
