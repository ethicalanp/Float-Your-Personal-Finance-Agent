import { test, expect } from "@playwright/test";

const PUBLIC_AND_SHELL_ROUTES = ["/", "/login", "/signup", "/privacy", "/terms", "/security", "/download"];
const AUTH_ROUTES = ["/home", "/plan", "/plan/recurring", "/protect", "/borrow", "/chat", "/profile"];

async function runDomA11yAudit(page: any, route: string) {
  const issues = await page.evaluate(() => {
    const problems: string[] = [];
    if (!document.documentElement.getAttribute("lang")) {
      problems.push("Missing <html lang>");
    }
    const imgs = Array.from(document.querySelectorAll("img"));
    for (const img of imgs) {
      if (img.getAttribute("alt") === null) {
        problems.push(`Image missing alt: ${img.getAttribute("src")}`);
      }
    }
    const controls = Array.from(document.querySelectorAll("input, select, textarea"));
    for (const el of controls) {
      const id = el.getAttribute("id");
      const hasLabel = id ? Boolean(document.querySelector(`label[for="${id}"]`)) : false;
      const wrappedByLabel = Boolean(el.closest("label"));
      const hasAria =
        Boolean(el.getAttribute("aria-label")) ||
        Boolean(el.getAttribute("aria-labelledby")) ||
        Boolean(el.getAttribute("placeholder"));
      if (!hasLabel && !wrappedByLabel && !hasAria && (el as HTMLInputElement).type !== "hidden") {
        problems.push(`Unlabeled control: ${el.tagName} name=${el.getAttribute("name")}`);
      }
    }
    const overflow = document.documentElement.scrollWidth > document.documentElement.clientWidth + 2;
    if (overflow) {
      problems.push(
        `Horizontal overflow: scrollWidth=${document.documentElement.scrollWidth} > clientWidth=${document.documentElement.clientWidth}`
      );
    }
    return problems;
  });
  expect(issues, `A11y/layout issues on ${route}: ${issues.join("; ")}`).toEqual([]);
}

test.describe("Cross-browser, Both Themes, Keyboard & A11y Audit", () => {
  test("Public pages pass a11y/layout checks in light and dark themes", async ({ page }) => {
    for (const theme of ["light", "dark"] as const) {
      await page.addInitScript((t) => {
        localStorage.setItem("float_theme", t);
      }, theme);
      for (const route of PUBLIC_AND_SHELL_ROUTES) {
        await page.goto(route);
        await expect(page.locator("body")).toBeVisible();
        await runDomA11yAudit(page, `${route} (${theme})`);
      }
    }
  });

  test("Keyboard-only navigation activates skip link and navigates login form", async ({ page }) => {
    await page.goto("/login");
    await page.keyboard.press("Tab");
    const focusedHref = await page.evaluate(() => document.activeElement?.getAttribute("href"));
    expect(focusedHref).toBe("#main-content");
    await page.keyboard.press("Enter");
    const mainId = await page.evaluate(() => document.activeElement?.getAttribute("id"));
    expect(mainId).toBe("main-content");
  });

  test("Authenticated app pages pass a11y/layout checks with mocked BFF auth", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("float_theme", "dark");
    });
    await page.route("**/api/**", async (route) => {
      const url = route.request().url();
      if (url.includes("/api/auth/me")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ user_id: "u1", email: "demo@float.internal", full_name: "Demo", consent_granted: true }),
        });
      }
      if (url.includes("/api/backend/api/v1/plan/budget")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ current: null, actuals: null, warnings: [] }),
        });
      }
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });

    for (const route of AUTH_ROUTES) {
      await page.goto(route);
      await expect(page.locator("body")).toBeVisible();
      await runDomA11yAudit(page, `${route} (dark)`);
    }
  });
});
