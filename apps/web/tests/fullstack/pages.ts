import { expect, type Browser, type Page } from "@playwright/test";

export async function createUniqueUserAndContext(
  browser: Browser,
  baseURL: string,
  prefix = "e2e",
) {
  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();
  const email = `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}@example.com`;
  const password = "StrongPassword123!";

  await page.goto("/signup");
  await page.locator("#fullName").fill("Fullstack Tester");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(password);
  const ageCheckbox = page.getByLabel("I confirm that I am 18 years of age or older.");
  if (await ageCheckbox.isVisible()) {
    await ageCheckbox.check();
  }
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/home/, { timeout: 15_000 });

  // Grant AI data processing consent via real BFF endpoint so /chat & /protect work seamlessly
  await page.evaluate(async () => {
    await fetch("/api/auth/consent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        terms_accepted: true,
        privacy_accepted: true,
        ai_data_processing_consent: true,
        consent_version: "2026.1",
      }),
    });
  });

  const state = await context.storageState();
  return { context, page, email, password, state };
}

export async function runBasicA11yAndThemeCheck(page: Page, route: string) {
  for (const theme of ["light", "dark"] as const) {
    await page.evaluate((t) => {
      localStorage.setItem("float_theme", t);
      document.documentElement.classList.toggle("dark", t === "dark");
    }, theme);
    const issues = await page.evaluate(() => {
      const problems: string[] = [];
      if (!document.documentElement.getAttribute("lang")) problems.push("Missing <html lang>");
      if (document.documentElement.scrollWidth > document.documentElement.clientWidth + 2) {
        problems.push(`Horizontal overflow: ${document.documentElement.scrollWidth} > ${document.documentElement.clientWidth}`);
      }
      return problems;
    });
    expect(issues, `A11y/layout issues on ${route} (${theme})`).toEqual([]);
  }
}

export class CalculatorsPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/plan/calculators");
    await expect(this.page.getByTestId("sip-convention")).toBeVisible();
  }

  async calculateForwardStepUp(opts: {
    monthlySip: string;
    years: string;
    returnPct: string;
    stepUpType: "none" | "percent" | "amount";
    stepUpInterval?: "1" | "2" | "3" | "6" | "12";
    stepUpPercent?: string;
    adjustInflation?: boolean;
  }) {
    await this.page.getByTestId("sip-mode-forward").click();
    await this.page.getByTestId("sip-monthly-input").fill(opts.monthlySip);
    await this.page.getByTestId("sip-years-input").fill(opts.years);
    await this.page.getByTestId("sip-return-input").fill(opts.returnPct);
    await this.page.getByTestId("sip-stepup-type").selectOption(opts.stepUpType);
    if (opts.stepUpType !== "none" && opts.stepUpInterval) {
      await this.page.getByTestId("sip-stepup-interval").selectOption(opts.stepUpInterval);
    }
    if (opts.stepUpType === "percent" && opts.stepUpPercent !== undefined) {
      await this.page.getByTestId("sip-stepup-percent").fill(opts.stepUpPercent);
    }
    const infToggle = this.page.getByTestId("sip-inflation-toggle");
    if (opts.adjustInflation === false && (await infToggle.isChecked())) {
      await infToggle.uncheck();
    } else if (opts.adjustInflation === true && !(await infToggle.isChecked())) {
      await infToggle.check();
    }
    await this.page.getByTestId("run-sip-btn").click();
    await expect(this.page.getByTestId("sip-result")).toBeVisible();
  }
}
