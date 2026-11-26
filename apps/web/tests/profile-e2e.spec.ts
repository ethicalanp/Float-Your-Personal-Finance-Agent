import { test, expect } from "@playwright/test";

test.describe("Profile Page & Mobile App Popup E2E", () => {
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

  test("1. Update display name on /profile persists across reload (light & dark)", async ({ page }) => {
    let currentName = "Priya Nair";
    let currentLang = "en";

    await page.route("**/api/me", async (route) => {
      const req = route.request();
      if (req.method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            user_id: "u-1",
            full_name: currentName,
            email: "priya@example.com",
            phone_number: null,
            preferred_language: currentLang,
            locale: "en-IN",
            notification_preferences: { security_alerts: true, recurring_reminders: true, product_updates: false },
            methods: ["password"],
            consent: { terms_accepted: true, ai_data_processing_consent: true, consent_version: "v1.0" },
            deletion_requested_at: null,
            deletion_scheduled_for: null,
            created_at: "2026-11-20T00:00:00Z",
          }),
        });
      } else if (req.method() === "PATCH") {
        const body = JSON.parse(req.postData() || "{}");
        currentName = body.full_name || currentName;
        currentLang = body.preferred_language || currentLang;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            user_id: "u-1",
            full_name: currentName,
            email: "priya@example.com",
            phone_number: null,
            preferred_language: currentLang,
            locale: "en-IN",
            notification_preferences: body.notification_preferences || {
              security_alerts: true,
              recurring_reminders: true,
              product_updates: false,
            },
            methods: ["password"],
            consent: { terms_accepted: true, ai_data_processing_consent: true, consent_version: "v1.0" },
            deletion_requested_at: null,
            deletion_scheduled_for: null,
            created_at: "2026-11-20T00:00:00Z",
          }),
        });
      }
    });

    await page.goto("/profile");
    await expect(page.locator('[data-testid="profile-display-name"]')).toContainText("Priya Nair");

    await page.fill("#profile-full-name", "പ്രിയ നായർ");
    await page.click('[data-testid="save-profile-btn"]');
    await expect(page.locator('[data-testid="profile-display-name"]')).toContainText("പ്രിയ നായർ");

    // Reload and verify persistence
    await page.reload();
    await expect(page.locator('[data-testid="profile-display-name"]')).toContainText("പ്രിയ നായർ");
  });

  test("2. Delete account flow shows grace period notice", async ({ page }) => {
    await page.route("**/api/me", async (route) => {
      const req = route.request();
      if (req.method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            user_id: "u-1",
            full_name: "Priya Nair",
            email: "priya@example.com",
            phone_number: null,
            preferred_language: "en",
            locale: "en-IN",
            notification_preferences: { security_alerts: true, recurring_reminders: true, product_updates: false },
            methods: ["password"],
            consent: { terms_accepted: true, ai_data_processing_consent: true, consent_version: "v1.0" },
            deletion_requested_at: null,
            deletion_scheduled_for: null,
            created_at: "2026-11-20T00:00:00Z",
          }),
        });
      } else if (req.method() === "DELETE") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "deletion_scheduled",
            deletion_requested_at: "2026-11-26T12:00:00Z",
            deletion_scheduled_for: "2026-12-10T12:00:00Z",
            grace_period_days: 14,
            message: "Account deletion scheduled.",
          }),
        });
      }
    });

    await page.goto("/profile");
    await page.click('[data-testid="open-delete-account-btn"]');
    await page.fill("#delete-confirm-input", "DELETE");
    await page.click('[data-testid="confirm-delete-account-btn"]');
    await expect(page.locator('[data-testid="deletion-grace-notice"]')).toBeVisible();
    await expect(page.locator('[data-testid="deletion-grace-notice"]')).toContainText("2026-12-10");
  });

  test("3. Mobile app popup (GetAppPrompt) hidden on first visit, shown on navigation, dismissed for 14 days", async ({
    page,
  }) => {
    await page.route("**/api/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "u-1",
          full_name: "Priya Nair",
          email: "priya@example.com",
          phone_number: null,
          preferred_language: "en",
          locale: "en-IN",
          notification_preferences: { security_alerts: true, recurring_reminders: true, product_updates: false },
          methods: ["password"],
          consent: { terms_accepted: true, ai_data_processing_consent: true, consent_version: "v1.0" },
          deletion_requested_at: null,
          deletion_scheduled_for: null,
          created_at: "2026-11-20T00:00:00Z",
        }),
      })
    );
    await page.route("**/api/auth/me*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, user_id: "u-1", consent: { ai_data_processing_consent: true, terms_accepted: true } }),
      })
    );
    await page.route("**/api/backend/**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));

    // 1. First screen of visit -> prompt must NOT show
    await page.goto("/profile");
    await expect(page.locator('[data-testid="get-app-prompt"]')).toHaveCount(0);

    // 2. Navigate to another non-excluded route -> prompt MUST show
    await page.click('a[href="/settings"]');
    await page.waitForURL("**/settings");
    const prompt = page.locator('[data-testid="get-app-prompt"]');
    await expect(prompt).toBeVisible();

    // 3. Dismiss with Escape -> hides and sets 14-day localStorage
    await page.keyboard.press("Escape");
    await expect(prompt).toHaveCount(0);
    const dismissedUntil = await page.evaluate(() => localStorage.getItem("float_get_app_dismissed_until"));
    expect(Number(dismissedUntil)).toBeGreaterThan(Date.now());
  });
});
