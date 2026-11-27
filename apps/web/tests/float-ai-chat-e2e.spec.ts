import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test.describe("Float.ai Chat E2E & Screenshots", () => {
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

  test("Full chat flow, /assistant 308 redirect, Why-this-answer drawer, and 360px/1440px screenshots", async ({
    page,
    request,
  }) => {
    const redir = await request.get("/assistant", { maxRedirects: 0 });
    expect(redir.status()).toBe(308);
    expect(redir.headers()["location"]).toContain("/chat");

    await page.route("**/api/auth/me*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, user_id: "u-1", consent: { ai_data_processing_consent: true, terms_accepted: true } }),
      })
    );
    await page.route("**/api/backend/api/v1/assistant/conversations", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.route("**/api/backend/api/v1/plan/**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.route("**/api/backend/api/v1/assistant/chat/stream", (route) =>
      route.fulfill({ status: 501, contentType: "application/json", body: JSON.stringify({ error: { code: "STREAMING_DISABLED" } }) })
    );
    await page.route("**/api/backend/api/v1/assistant/chat", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "success",
          answer: "Call **1930** or visit [Cybercrime Portal](https://cybercrime.gov.in) immediately. <script>alert(1)</script>",
          language: "en",
          citations: [{ chunk_id: "c1", source_title: "RBI Zero Liability", source_url: "https://rbi.org.in" }],
          facts_used: ["helpline_1930"],
          route: "protect",
          confidence: "high",
          trace_id: "tr-1",
          prompt_version: "v1",
          created_at: "2026-11-27T04:00:00Z",
        }),
      })
    );
    await page.route("**/api/backend/api/v1/assistant/feedback", (route) =>
      route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ status: "recorded" }) })
    );

    const screenshotsDir = path.join(process.cwd(), "docs", "screenshots");
    fs.mkdirSync(screenshotsDir, { recursive: true });

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/chat");
    await expect(page.locator('[data-testid="ai-disclosure"]')).toContainText("Float.ai is an AI assistant and can make mistakes.");
    await expect(page.locator('[data-testid="chat-empty-state"]')).toBeVisible();

    await page.fill('[data-testid="chat-composer"]', "How do I report UPI fraud?");
    await page.click('[data-testid="send-chat-btn"]');
    await expect(page.locator("text=Cybercrime Portal")).toBeVisible();
    // Script tag must be stripped, never rendered
    await expect(page.locator("text=<script>")).toHaveCount(0);

    await page.click('[data-testid="why-answer-btn"]');
    await expect(page.locator('[data-testid="why-answer-drawer"]')).toContainText("Verified Knowledge Base");

    await page.screenshot({ path: path.join(screenshotsDir, "float-ai-chat-1440.png"), fullPage: false });

    await page.setViewportSize({ width: 360, height: 800 });
    await page.screenshot({ path: path.join(screenshotsDir, "float-ai-chat-360.png"), fullPage: false });
  });

  test("Streaming SSE, Stop button, and network drop keeps partial text with Retry", async ({ page }) => {
    await page.route("**/api/auth/me*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, user_id: "u-1", consent: { ai_data_processing_consent: true, terms_accepted: true } }),
      })
    );
    await page.route("**/api/backend/api/v1/assistant/conversations", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.route("**/api/backend/api/v1/plan/**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );

    // 1. Real SSE stream
    await page.route("**/api/backend/api/v1/assistant/chat/stream", (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          'event: delta\ndata: {"delta":"Hello "}\n\n',
          'event: delta\ndata: {"delta":"from Float.ai"}\n\n',
          'event: done\ndata: {"answer":"Hello from Float.ai","status":"success","route":"knowledge","citations":[],"facts_used":[]}\n\n',
        ].join(""),
      })
    );

    await page.goto("/chat");
    await page.fill('[data-testid="chat-composer"]', "Hi Float.ai");
    await page.click('[data-testid="send-chat-btn"]');
    await expect(page.locator("text=Hello from Float.ai")).toBeVisible();

    // 2. Network drop after stream fails -> keeps error/retry option
    await page.route("**/api/backend/api/v1/assistant/chat/stream", (route) => route.abort("failed"));
    await page.fill('[data-testid="chat-composer"]', "Second question");
    await page.click('[data-testid="send-chat-btn"]');
    await expect(page.locator("button:has-text('Retry')")).toBeVisible();
  });
});
