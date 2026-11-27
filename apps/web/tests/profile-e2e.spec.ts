import { test, expect } from "@playwright/test";

const MOCK_ME = {
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
};

test.describe("Profile, Settings & App-wide Bug Sweep E2E", () => {
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

  test("1. Update display name on /profile persists across reload and Profile menu opens /profile/settings", async ({ page }) => {
    let currentName = "Priya Nair";
    let currentLang = "en";

    await page.route("**/api/me", async (route) => {
      const req = route.request();
      if (req.method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ...MOCK_ME, full_name: currentName, preferred_language: currentLang }),
        });
      } else if (req.method() === "PATCH") {
        const body = JSON.parse(req.postData() || "{}");
        currentName = body.full_name || currentName;
        currentLang = body.preferred_language || currentLang;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            ...MOCK_ME,
            full_name: currentName,
            preferred_language: currentLang,
            notification_preferences: body.notification_preferences || MOCK_ME.notification_preferences,
          }),
        });
      }
    });

    await page.goto("/profile");
    await expect(page.locator('[data-testid="profile-display-name"]')).toContainText("Priya Nair");
    // Settings is NOT in top-level nav
    await expect(page.locator('header nav a[href="/settings"]')).toHaveCount(0);

    await page.fill("#profile-full-name", "പ്രിയ നായർ");
    await page.click('[data-testid="save-profile-btn"]');
    await expect(page.locator('[data-testid="profile-display-name"]')).toContainText("പ്രിയ നായർ");

    await page.reload();
    await expect(page.locator('[data-testid="profile-display-name"]')).toContainText("പ്രിയ നായർ");

    // Open Profile menu -> Settings
    await page.click('[data-testid="profile-menu-btn"]');
    await page.click('[data-testid="profile-menu-settings"]');
    await page.waitForURL("**/profile/settings");
    await expect(page.locator("h1")).toContainText("Settings");
  });

  test("2. /settings 308 redirects to /profile/settings and delete account flow shows grace period notice", async ({ page, request }) => {
    const redirectRes = await request.get("/settings", { maxRedirects: 0 });
    expect(redirectRes.status()).toBe(308);
    expect(redirectRes.headers()["location"]).toContain("/profile/settings");

    await page.route("**/api/me", async (route) => {
      const req = route.request();
      if (req.method() === "GET") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_ME) });
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
    await page.route("**/api/auth/me*", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, user_id: "u-1", consent: MOCK_ME.consent }) })
    );
    await page.route("**/api/auth/capabilities", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ google: false, phone: false, email: true }) })
    );
    await page.route("**/api/auth/methods", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ has_password: true, methods: [] }) })
    );
    await page.route("**/api/auth/sessions", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ sessions: [] }) })
    );

    await page.goto("/profile/settings");
    await page.click('[data-testid="open-delete-account-btn"]');
    await page.fill("#delete-confirm-input", "DELETE");
    await page.click('[data-testid="confirm-delete-account-btn"]');
    await expect(page.locator('[data-testid="deletion-grace-notice"]')).toBeVisible();
    await expect(page.locator('[data-testid="deletion-grace-notice"]')).toContainText("2026");
  });

  test("3. Mobile app popup (GetAppPrompt) hidden on first visit, shown on navigation, dismissed for 14 days", async ({
    page,
  }) => {
    await page.route("**/api/me", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_ME) })
    );
    await page.route("**/api/auth/me*", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, user_id: "u-1", consent: MOCK_ME.consent }) })
    );
    await page.route("**/api/auth/capabilities", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ google: false, phone: false, email: true }) })
    );
    await page.route("**/api/auth/methods", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ has_password: true, methods: [] }) })
    );
    await page.route("**/api/auth/sessions", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ sessions: [] }) })
    );
    await page.route("**/api/backend/**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));

    await page.goto("/profile");
    await expect(page.locator('[data-testid="get-app-prompt"]')).toHaveCount(0);

    await page.click('[data-testid="open-profile-settings-link"]');
    await page.waitForURL("**/profile/settings");
    const prompt = page.locator('[data-testid="get-app-prompt"]');
    await expect(prompt).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(prompt).toHaveCount(0);
    const dismissedUntil = await page.evaluate(() => localStorage.getItem("float_get_app_dismissed_until"));
    expect(Number(dismissedUntil)).toBeGreaterThan(Date.now());
  });

  test("4. Bug sweep: every page in light & dark themes has 0 console errors, 0 hydration warnings, 0 CSP violations, and valid landmarks", async ({
    page,
    context,
  }) => {
    await page.route("**/api/me", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_ME) })
    );
    await page.route("**/api/auth/me*", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, user_id: "u-1", consent: MOCK_ME.consent }) })
    );
    await page.route("**/api/auth/capabilities", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ google: false, phone: false, email: true }) })
    );
    await page.route("**/api/auth/methods", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ has_password: true, methods: [] }) })
    );
    await page.route("**/api/auth/sessions", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ sessions: [] }) })
    );
    await page.route("**/api/backend/**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ accounts: [], transactions: [], commitments: [], alerts: [], contacts: [], cases: [] }) })
    );

    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    const cspViolations: string[] = [];

    let currentRoute = "";
    page.on("console", (msg) => {
      const text = msg.text();
      if (msg.type() === "error" || /hydration|did not match/i.test(text)) {
        consoleErrors.push(`${currentRoute} ${msg.type()}: ${text}`);
      }
    });
    page.on("pageerror", (err) => pageErrors.push(`${currentRoute}: ${err.message}`));
    await page.addInitScript(() => {
      document.addEventListener("securitypolicyviolation", (e) => {
        (window as any).__cspViolations = (window as any).__cspViolations || [];
        (window as any).__cspViolations.push(`${e.violatedDirective}: ${e.blockedURI}`);
      });
    });

    const authedPages = ["/home", "/protect", "/borrow", "/assistant", "/profile", "/profile/settings", "/consent"];
    const publicPages = ["/", "/download"];

    for (const theme of ["light", "dark"] as const) {
      await page.addInitScript((t) => localStorage.setItem("float_theme", t), theme);
      for (const path of [...publicPages, ...authedPages]) {
        currentRoute = `${path} (${theme})`;
        await page.goto(path, { waitUntil: "domcontentloaded" });
        await expect(page.locator("main")).toBeVisible();
        const csp = await page.evaluate(() => (window as any).__cspViolations || []);
        if (csp.length) cspViolations.push(`${path} (${theme}): ${csp.join("; ")}`);
      }
    }

    // Check /login and /signup without auth cookie
    await context.clearCookies();
    for (const theme of ["light", "dark"] as const) {
      await page.addInitScript((t) => localStorage.setItem("float_theme", t), theme);
      for (const path of ["/login", "/signup"]) {
        currentRoute = `${path} (${theme})`;
        await page.goto(path, { waitUntil: "domcontentloaded" });
        await expect(page.locator("h1")).toBeVisible();
      }
    }

    expect(consoleErrors, `Console/hydration errors: ${consoleErrors.join(" | ")}`).toEqual([]);
    expect(pageErrors, `Page errors: ${pageErrors.join(" | ")}`).toEqual([]);
    expect(cspViolations, `CSP violations: ${cspViolations.join(" | ")}`).toEqual([]);
  });
});
