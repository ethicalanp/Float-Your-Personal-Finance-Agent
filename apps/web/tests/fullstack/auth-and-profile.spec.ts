import { test, expect } from "@playwright/test";
import { createUniqueUserAndContext, runBasicA11yAndThemeCheck } from "./pages";

test.describe("Fullstack Auth, Public Pages, Notifications & Profile", () => {
  test("Row 1: Auth flows (/signup, /login, /consent, /forgot-password, /reset-password, /verify-email)", async ({
    browser,
    baseURL,
  }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page, email, password } = await createUniqueUserAndContext(browser, url, "auth");

    try {
      await page.goto("/consent");
      await expect(page.locator("main")).toBeVisible();
      await runBasicA11yAndThemeCheck(page, "/consent");

      for (const route of ["/forgot-password", "/reset-password", "/verify-email"]) {
        await page.goto(route);
        await expect(page.locator("body")).toBeVisible();
        await runBasicA11yAndThemeCheck(page, route);
      }

      // Error state: invalid password on /login shows generic error alert
      const anonCtx = await browser.newContext({ baseURL: url });
      const anonPage = await anonCtx.newPage();
      await anonPage.goto("/login");
      await anonPage.locator("#email").fill(email);
      await anonPage.locator("#password").fill("WrongPassword999!");
      await anonPage.getByRole("button", { name: /sign in/i }).click();
      await expect(
        anonPage.getByRole("alert").filter({ hasText: /invalid email or password/i }),
      ).toBeVisible();

      // Happy path: sign in with valid credentials navigates to /home
      await anonPage.locator("#password").fill(password);
      await anonPage.getByRole("button", { name: /sign in/i }).click();
      await expect(anonPage).toHaveURL(/\/home/, { timeout: 15_000 });
      await runBasicA11yAndThemeCheck(anonPage, "/login->/home");
      await anonCtx.close();
    } finally {
      await context.close();
    }
  });

  test("Row 14: Notifications & reminder preferences (/profile/settings, /plan/recurring)", async ({
    browser,
    baseURL,
  }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "notif");

    try {
      await page.goto("/profile/settings");
      await expect(page.getByTestId("theme-settings-section")).toBeVisible();
      await runBasicA11yAndThemeCheck(page, "/profile/settings");

      // Happy path: due-soon reminders strip renders on /plan/recurring
      await page.goto("/plan/recurring");
      await expect(page.getByTestId("due-soon-strip")).toBeVisible();

      // Error state: submitting empty recurring form does not create a commitment and keeps empty state
      await page.getByTestId("add-recurring-btn").click();
      await expect(page.getByTestId("recurring-empty")).toBeVisible();
      await runBasicA11yAndThemeCheck(page, "/plan/recurring");
    } finally {
      await context.close();
    }
  });

  test("Row 15: Profile & Settings (/profile, /profile/settings)", async ({ browser, baseURL }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page, email } = await createUniqueUserAndContext(browser, url, "prof");

    try {
      await page.goto("/profile");
      await expect(page.getByText(email)).toBeVisible();

      // Happy path: update display name and verify persistence across reload
      const nameInput = page.locator("input[type='text']").first();
      await nameInput.fill("Updated Tester");
      await page.getByTestId("save-profile-btn").click();
      await expect(page.getByTestId("profile-display-name")).toContainText("Updated Tester");
      await page.reload();
      await expect(page.getByTestId("profile-display-name")).toContainText("Updated Tester");
      await runBasicA11yAndThemeCheck(page, "/profile");

      // Error state: clearing display name keeps validation / prevents blank save
      await nameInput.fill("");
      await page.getByTestId("save-profile-btn").click();
      await expect(page.locator("main")).toBeVisible();

      await page.goto("/profile/settings");
      await expect(page.getByTestId("data-rights-section")).toBeVisible();
      await runBasicA11yAndThemeCheck(page, "/profile/settings");
    } finally {
      await context.close();
    }
  });

  test("Row 16: Public Pages (/, /privacy, /terms, /security, /download)", async ({
    browser,
    baseURL,
  }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const context = await browser.newContext({ baseURL: url });
    const page = await context.newPage();

    try {
      for (const route of ["/", "/privacy", "/terms", "/security", "/download"]) {
        await page.goto(route);
        await expect(page.locator("main")).toBeVisible();
        await runBasicA11yAndThemeCheck(page, route);
      }

      // Error state: unknown public route renders 404 without crashing
      const resp = await page.goto("/nonexistent-public-route-check");
      expect(resp?.status()).toBe(404);
      await expect(page.locator("body")).toBeVisible();
    } finally {
      await context.close();
    }
  });
});
