import { test, expect } from "@playwright/test";

test.describe("Login E2E Flow, Hardening, and Error Handling", () => {
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

    // Default mock capabilities
    await page.route("**/api/auth/capabilities*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ google: true, phone: true, email: true }),
      })
    );

    // Default mock user session and app data
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
          top_categories: [{ category: "Salary", total_amount: 90000, count: 1 }],
          monthly_breakdown: [{ month: "2026-11", inflow: 90000, outflow: 40000, net: 50000 }],
        }),
      })
    );
  });

  test("1. Successful login sets auth cookie and lands on /home", async ({ page, context }) => {
    await page.route("**/api/auth/login*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "set-cookie": "float_token=fake_test_jwt_token_for_e2e; Path=/; HttpOnly; SameSite=Lax",
        },
        body: JSON.stringify({
          ok: true,
          user: { id: "mock-user-1", email: "priya@example.com", full_name: "Priya Sharma" },
        }),
      });
    });

    await page.goto("/login");
    await expect(page.locator("h1")).toContainText("Welcome back to Float");

    await page.fill('input[type="email"]', "priya@example.com");
    await page.fill('input[type="password"]', "ValidPassword123!");
    await page.click('button[type="submit"]');

    // Should transition to /home
    await page.waitForURL("**/home", { timeout: 10000 });
    expect(page.url()).toContain("/home");

    // Check cookie
    const cookies = await context.cookies();
    const authCookie = cookies.find((c) => c.name === "float_token");
    expect(authCookie).toBeDefined();

    // Zero CSP violations
    expect((page as any).__cspViolations).toEqual([]);
    const spv = await page.evaluate(() => (window as any).__securityPolicyViolations || []);
    expect(spv).toEqual([]);
  });

  test("2. Wrong password stays on /login, shows friendly error with Request ID, retains email", async ({ page }) => {
    await page.route("**/api/auth/login*", async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "INVALID_CREDENTIALS",
            message: "Invalid email or password.",
            request_id: "req_test_401_abc",
          },
        }),
      });
    });

    await page.goto("/login");
    await page.fill('input[type="email"]', "user@example.com");
    await page.fill('input[type="password"]', "WrongPassword!");
    await page.click('button[type="submit"]');

    // Remains on /login
    expect(page.url()).toContain("/login");

    // Shows friendly error with Request ID
    const errorAlert = page.locator('div[role="alert"]:not(#__next-route-announcer__)');
    await expect(errorAlert).toBeVisible();
    await expect(errorAlert).toContainText("Invalid email or password.");
    await expect(errorAlert).toContainText("Request ID: req_test_401_abc");

    // Retains email input
    const emailInput = page.locator('input[type="email"]');
    await expect(emailInput).toHaveValue("user@example.com");

    // Zero CSP violations
    expect((page as any).__cspViolations).toEqual([]);
    const spv = await page.evaluate(() => (window as any).__securityPolicyViolations || []);
    expect(spv).toEqual([]);
  });

  test("3. Phone OTP flow (Request OTP -> Verify OTP) navigates to /home", async ({ page, context }) => {
    await page.route("**/api/auth/phone/request*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          message: "A 6-digit OTP code has been sent to your phone.",
          cooldown_seconds: 30,
        }),
      });
    });

    await page.route("**/api/auth/phone/verify*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "set-cookie": "float_token=fake_phone_jwt_token; Path=/; HttpOnly; SameSite=Lax",
        },
        body: JSON.stringify({
          ok: true,
          user: { id: "mock-user-2", phone_number: "+919876543210" },
        }),
      });
    });

    await page.goto("/login");

    // Switch to Phone OTP tab
    await page.click('button:has-text("Phone OTP")');
    const phoneInput = page.locator('input[type="tel"]');
    await expect(phoneInput).toBeVisible();

    await phoneInput.fill("+919876543210");
    await page.click('button:has-text("Send OTP")');

    // OTP form appears
    const otpInput = page.locator('input[id="otp"]');
    await expect(otpInput).toBeVisible();

    await otpInput.fill("123456");
    await page.click('button:has-text("Verify & Sign In")');

    // Navigates to /home
    await page.waitForURL("**/home", { timeout: 10000 });
    expect(page.url()).toContain("/home");

    // Cookie is set
    const cookies = await context.cookies();
    const authCookie = cookies.find((c) => c.name === "float_token");
    expect(authCookie).toBeDefined();
  });

  test("4. Google button container/fallback renders with zero CSP violations, forgot/reset password", async ({ page }) => {
    // Note: Real Google OAuth popup cannot be automated in headless E2E; we verify the GIS container/fallback
    // renders cleanly with zero CSP errors and test the BFF error mapping via mocked window.google callback.
    await page.route("**/api/auth/google*", async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "UNAUTHORIZED",
            message: "Invalid or expired Google ID token.",
            request_id: "req_google_err_999",
          },
        }),
      });
    });

    await page.addInitScript(() => {
      let savedCallback: ((res: { credential?: string }) => void) | null = null;
      (window as any).google = {
        accounts: {
          id: {
            initialize(cfg: any) {
              savedCallback = cfg.callback;
            },
            renderButton(el: HTMLElement) {
              const btn = document.createElement("button");
              btn.type = "button";
              btn.textContent = "Continue with Google";
              btn.onclick = () => savedCallback?.({ credential: "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.sig" });
              el.appendChild(btn);
            },
          },
        },
      };
    });

    await page.route("**/api/auth/capabilities*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ google: true, phone: true, email: true, google_client_id: "test-client-id" }),
      })
    );

    await page.goto("/login");

    // Verify Google Sign-In container renders either the GIS button or friendly blocked fallback
    const googleContainer = page.locator('[data-testid="google-login-btn"]');
    await expect(googleContainer).toBeVisible();

    const renderedBtn = googleContainer.locator("button:has-text('Continue with Google')");
    await expect(renderedBtn).toBeVisible();
    await renderedBtn.click();

    // Check error alert shows generic message and Request ID
    const alert = page.locator('div[role="alert"]:not(#__next-route-announcer__)');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("Invalid or expired Google ID token");
    await expect(alert).toContainText("Request ID: req_google_err_999");

    // Zero CSP violations
    expect((page as any).__cspViolations).toEqual([]);
    const spv = await page.evaluate(() => (window as any).__securityPolicyViolations || []);
    expect(spv).toEqual([]);

    // Test Forgot Password navigation
    await page.click('a:has-text("Forgot password?")');
    await page.waitForURL("**/forgot-password", { timeout: 10000 });
    expect(page.url()).toContain("/forgot-password");

    // Test Reset Password page loads
    await page.goto("/reset-password?token=mock_valid_token");
    await expect(page.locator("h1")).toContainText("Set New Password");
  });
});
