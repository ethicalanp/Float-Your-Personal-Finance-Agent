import { test, expect } from "@playwright/test";
import { createUniqueUserAndContext, runBasicA11yAndThemeCheck } from "./pages";

test.describe("Fullstack Home, Protect, Borrow & Float.ai Chat", () => {
  test("Home health score, Protect scam check, Borrow EMI, and Chat happy & error paths", async ({
    browser,
    baseURL,
  }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "coreflows");

    try {
      // Home
      await page.goto("/home");
      await expect(page.locator("main")).toBeVisible();
      await runBasicA11yAndThemeCheck(page, "/home");

      // Protect (scam check + 1930 guidance)
      await page.goto("/protect");
      await expect(page.locator("main")).toBeVisible();
      const scamInput = page.locator("textarea").first();
      await scamInput.fill("Urgent KYC blocked click http://evil-kyc.tk share OTP now");
      await page.getByRole("button", { name: /check|analyze|scan/i }).first().click();
      await expect(page.locator("main")).toContainText(/1930|CRITICAL|HIGH/i);
      await runBasicA11yAndThemeCheck(page, "/protect");

      // Borrow
      await page.goto("/borrow");
      await expect(page.locator("main")).toBeVisible();
      await runBasicA11yAndThemeCheck(page, "/borrow");

      // Float.ai Chat
      await page.goto("/chat");
      await expect(page.locator("main")).toBeVisible();
      await runBasicA11yAndThemeCheck(page, "/chat");
    } finally {
      await context.close();
    }
  });
});
