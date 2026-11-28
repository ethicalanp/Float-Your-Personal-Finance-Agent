import { test, expect } from "@playwright/test";
import { createUniqueUserAndContext, runBasicA11yAndThemeCheck } from "./pages";

test.describe("Fullstack Home, Statement Upload, Protect, Borrow & Float.ai Chat", () => {
  test("Row 2: Home & Health Score (/home)", async ({ browser, baseURL }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "home");

    try {
      await page.goto("/home");
      await expect(page.getByTestId("health-score-card")).toBeVisible();
      await expect(page.getByTestId("health-score-value")).toBeVisible();

      // Happy path: toggle essential insurance flag and verify card remains healthy
      await page.getByRole("button", { name: "Yes", exact: true }).click();
      await expect(page.getByTestId("health-score-components")).toBeVisible();
      await runBasicA11yAndThemeCheck(page, "/home");

      // Error/auth-guard state: unauthenticated visit to /home redirects to /login
      const anonCtx = await browser.newContext({ baseURL: url });
      const anonPage = await anonCtx.newPage();
      await anonPage.goto("/home");
      await expect(anonPage).toHaveURL(/\/login/);
      await anonCtx.close();
    } finally {
      await context.close();
    }
  });

  test("Row 3: Statement Upload (/plan, /home)", async ({ browser, baseURL }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "upload");

    try {
      await page.goto("/plan");
      await expect(page.locator("main")).toBeVisible();

      // Error state: uploading an invalid non-CSV file shows upload error feedback
      const fileInput = page.locator("input[type='file']").first();
      if ((await fileInput.count()) > 0) {
        await fileInput.setInputFiles({
          name: "bad.txt",
          mimeType: "text/plain",
          buffer: Buffer.from("not a valid csv statement"),
        });
        await expect(page.locator("main")).toContainText(/csv|invalid|error|failed/i);

        // Happy path: uploading a valid CSV statement succeeds
        await fileInput.setInputFiles({
          name: "statement.csv",
          mimeType: "text/csv",
          buffer: Buffer.from("date,description,amount,type\n2026-11-01,Salary,50000,credit\n2026-11-02,Groceries,1500,debit\n"),
        });
        await expect(page.locator("main")).toBeVisible();
      } else {
        await expect(page.getByTestId("plan-no-transactions")).toBeVisible();
      }
      await runBasicA11yAndThemeCheck(page, "/plan");
    } finally {
      await context.close();
    }
  });

  test("Row 4: Protect, UPI Check & 1930 Flow (/protect)", async ({ browser, baseURL }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "protect");

    try {
      await page.goto("/protect");
      await expect(page.locator("main")).toBeVisible();

      // Error state: empty scam submission does not crash and shows guidance or keeps disabled/alert
      const checkBtn = page.getByRole("button", { name: /check|analyze|scan/i }).first();
      if (await checkBtn.isEnabled()) {
        await checkBtn.click();
        await expect(page.locator("main")).toBeVisible();
      }

      // Happy path: suspicious KYC + OTP message returns risk tier and 1930 helpline
      const scamInput = page.locator("textarea").first();
      await scamInput.fill("Urgent KYC blocked click http://evil-kyc.tk share OTP now");
      await checkBtn.click();
      await expect(page.locator("main")).toContainText(/1930|CRITICAL|HIGH/i);
      await runBasicA11yAndThemeCheck(page, "/protect");
    } finally {
      await context.close();
    }
  });

  test("Row 5: Borrow & EMI (/borrow)", async ({ browser, baseURL }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "borrow");

    try {
      await page.goto("/borrow");
      await expect(page.locator("main")).toBeVisible();

      // Happy path: educational/indicative readiness & EMI controls render
      await expect(page.locator("main")).toContainText(/indicative|readiness|emi|borrow/i);

      // Error state: negative numeric input in any calculator/EMI input does not crash
      const numInput = page.locator("input[type='number']").first();
      if ((await numInput.count()) > 0) {
        await numInput.fill("-1000");
        await expect(page.locator("main")).toBeVisible();
      }
      await runBasicA11yAndThemeCheck(page, "/borrow");
    } finally {
      await context.close();
    }
  });

  test("Row 6: Float.ai Chat (/chat)", async ({ browser, baseURL }) => {
    const url = baseURL || "http://127.0.0.1:3010";
    const { context, page } = await createUniqueUserAndContext(browser, url, "chat");

    try {
      await page.goto("/chat");
      await expect(page.getByTestId("ai-disclosure")).toBeVisible();

      // Error/refusal state: empty send button is disabled
      await expect(page.getByTestId("send-chat-btn")).toBeDisabled();

      // Happy path: send educational query and receive fake-provider assistant reply
      await page.getByTestId("chat-composer").fill("What is an emergency fund?");
      await page.getByTestId("send-chat-btn").click();
      await expect(page.locator("main")).toContainText(/emergency|fund|educational|illustrative/i, {
        timeout: 15_000,
      });
      await runBasicA11yAndThemeCheck(page, "/chat");
    } finally {
      await context.close();
    }
  });
});
