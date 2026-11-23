import { test, expect } from "@playwright/test";

test.describe("Float Landing Page Smoke Tests", () => {
  test("should render the complete landing page with all mandatory sections and copy", async ({
    page,
  }) => {
    // 1. Load the landing page
    const response = await page.goto("/");
    expect(response?.status()).toBe(200);

    // 2. Header and Logo placeholder check
    const logo = page.locator('[data-testid="logo-placeholder"]');
    await expect(logo).toBeVisible();
    await expect(logo).toContainText("Float");

    // Nav Links
    await expect(page.getByRole("link", { name: "Features" })).toBeVisible();
    await expect(page.getByRole("link", { name: "How it works" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Security" })).toBeVisible();
    await expect(page.getByRole("link", { name: "FAQ" })).toBeVisible();

    // 3. Hero Section check
    await expect(
      page.getByRole("heading", {
        name: /Plan your money.*Protect from scams.*Borrow responsibly/i,
      })
    ).toBeVisible();

    // Primary and Secondary CTAs
    await expect(page.getByRole("link", { name: "Sign up" }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Try the scam check" })).toBeVisible();

    // 4. Three Pillars check: Plan, Protect, Borrow
    const featuresSection = page.locator("#features");
    await expect(featuresSection).toBeVisible();
    await expect(featuresSection.getByRole("button", { name: /Plan/i })).toBeVisible();
    await expect(featuresSection.getByRole("button", { name: /Protect/i })).toBeVisible();
    await expect(featuresSection.getByRole("button", { name: /Borrow/i })).toBeVisible();

    // 5. How It Works Section check (4 steps)
    const howItWorks = page.locator("#how-it-works");
    await expect(howItWorks).toBeVisible();
    await expect(howItWorks.getByText("01")).toBeVisible();
    await expect(howItWorks.getByText("02")).toBeVisible();
    await expect(howItWorks.getByText("03")).toBeVisible();
    await expect(howItWorks.getByText("04")).toBeVisible();

    // 6. Security Section check (Honest safeguards)
    const security = page.locator("#security");
    await expect(security).toBeVisible();
    await expect(security.getByText("Masked Account Identifiers")).toBeVisible();
    await expect(security.getByText("Explicit Consent Architecture")).toBeVisible();

    // 7. FAQ Section check (Accordion interaction)
    const faq = page.locator("#faq");
    await expect(faq).toBeVisible();
    const firstFaqBtn = faq.getByRole("button", {
      name: /Is Float a credit score or credit bureau\?/i,
    });
    await expect(firstFaqBtn).toBeVisible();
    await expect(faq.getByText(/No\. Float is not a credit rating bureau/i)).toBeVisible();

    // 8. Footer Section check with Mandatory Disclaimer
    const footer = page.locator("footer");
    await expect(footer).toBeVisible();
    await expect(
      footer.getByText(
        "Float provides indicative information only. It is not a credit score, financial advice or a lender's decision."
      )
    ).toBeVisible();
  });

  test("should test the live scam check box and return real risk tier, score, and reasons", async ({
    page,
  }) => {
    await page.goto("/");

    const scamSection = page.locator("#live-check");
    await expect(scamSection).toBeVisible();

    const textarea = scamSection.locator("#scam-input");
    await expect(textarea).toBeVisible();

    // Test with a sample malicious APK urgency pattern
    const suspiciousMessage =
      "Dear consumer, your electricity power will be disconnected tonight at 9:30 PM. Immediately install KSEB.apk to avoid blackout.";
    await textarea.fill(suspiciousMessage);

    const checkButton = scamSection.getByRole("button", { name: /Check Message/i });
    await checkButton.click();

    // Expect the real API evaluation result box
    const resultBox = scamSection.locator('[data-testid="scam-check-result"]');
    await expect(resultBox).toBeVisible({ timeout: 10000 });

    // Verify Risk Tier verdict
    await expect(resultBox).toContainText(/Dangerous Threat Detected|DANGEROUS/i);

    // Verify Identified Reasons & Indicators
    await expect(resultBox).toContainText(/Identified Reasons & Triggers/i);
    await expect(resultBox).toContainText(
      /urgency|APK download attempt|external link/i
    );

    // Verify helpline guidance is surfaced
    await expect(resultBox).toContainText("1930");
  });
});
