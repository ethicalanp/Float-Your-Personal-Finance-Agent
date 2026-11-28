import { test, expect } from "@playwright/test";
import { createUniqueUserAndContext, runBasicA11yAndThemeCheck } from "./pages";

test.describe("Fullstack Auth, Public Pages & Profile", () => {
  test("Signup, invalid login error, profile & settings, and public routes", async ({
    browser,
    baseURL,
  }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page, email } = await createUniqueUserAndContext(browser, url, "authprof");

    try {
      // Public routes smoke & a11y
      for (const route of ["/", "/privacy", "/terms", "/security", "/download", "/forgot-password", "/reset-password", "/verify-email", "/consent"]) {
        await page.goto(route);
        await expect(page.locator("body")).toBeVisible();
        await runBasicA11yAndThemeCheck(page, route);
      }

      // Profile & Settings happy path + notification preferences
      await page.goto("/profile");
      await expect(page.getByText(email)).toBeVisible();
      await runBasicA11yAndThemeCheck(page, "/profile");

      await page.goto("/profile/settings");
      await expect(page.locator("main")).toBeVisible();
      await runBasicA11yAndThemeCheck(page, "/profile/settings");

      // Separate unauthenticated context: invalid login shows generic error without leaking existence
      const anonCtx = await browser.newContext({ baseURL: url });
      const anonPage = await anonCtx.newPage();
      await anonPage.goto("/login");
      await anonPage.locator("#email").fill(email);
      await anonPage.locator("#password").fill("WrongPassword999!");
      await anonPage.getByRole("button", { name: /sign in/i }).click();
      await expect(
        anonPage.getByRole("alert").filter({ hasText: /invalid email or password/i }),
      ).toBeVisible();
      await runBasicA11yAndThemeCheck(anonPage, "/login");
      await anonCtx.close();
    } finally {
      await context.close();
    }
  });
});
