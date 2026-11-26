import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

test.describe("Visual Check Screenshots & E2E Light/Dark Verification", () => {
  const screenshotsDir = path.join(process.cwd(), "docs", "screenshots");

  test.beforeAll(() => {
    if (!fs.existsSync(screenshotsDir)) {
      fs.mkdirSync(screenshotsDir, { recursive: true });
    }
  });

  test.beforeEach(async ({ page }) => {
    // Mock capabilities to show Google and Phone
    await page.route("**/api/auth/capabilities*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ google: true, phone: true, email: true }),
      })
    );
  });

  test("Desktop 1440px - Login Light and Dark Mode", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    // 1. Light Mode
    await page.goto("/login");
    await expect(page.locator("h1")).toContainText("Welcome back to Float");
    await expect(page.locator('[data-testid="google-login-btn"]')).toBeVisible();
    await expect(page.locator('[data-testid="phone-auth-option"]')).toBeVisible();
    await page.screenshot({ path: path.join(screenshotsDir, "login-1440px-light.png"), fullPage: true });

    // 2. Dark Mode
    await page.evaluate(() => {
      document.documentElement.setAttribute("data-scheme", "dark");
      document.documentElement.classList.add("dark");
    });
    await page.screenshot({ path: path.join(screenshotsDir, "login-1440px-dark.png"), fullPage: true });
  });

  test("Mobile 360px - Login Light and Dark Mode", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });

    // 1. Light Mode
    await page.goto("/login");
    await expect(page.locator("h1")).toContainText("Welcome back to Float");
    await expect(page.locator('[data-testid="google-login-btn"]')).toBeVisible();
    await page.screenshot({ path: path.join(screenshotsDir, "login-360px-light.png"), fullPage: true });

    // 2. Dark Mode
    await page.evaluate(() => {
      document.documentElement.setAttribute("data-scheme", "dark");
      document.documentElement.classList.add("dark");
    });
    await page.screenshot({ path: path.join(screenshotsDir, "login-360px-dark.png"), fullPage: true });
  });
});
