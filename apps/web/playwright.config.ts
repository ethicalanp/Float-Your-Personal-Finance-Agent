import { defineConfig, devices } from "@playwright/test";

const isFullstackRun =
  process.env.FULLSTACK_E2E === "1" ||
  process.argv.some((arg) => arg.includes("fullstack"));

export default defineConfig({
  testDir: "./tests",
  testMatch: /.*\.spec\.ts/,
  timeout: 45 * 1000,
  expect: {
    timeout: 7000,
  },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: "list",
  globalSetup: isFullstackRun ? "./tests/fullstack/global-setup.ts" : undefined,
  use: {
    baseURL: process.env.PLAYWRIGHT_TEST_BASE_URL || "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      testIgnore: /fullstack\/.*\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      testIgnore: /fullstack\/.*\.spec\.ts/,
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      testIgnore: /fullstack\/.*\.spec\.ts/,
      use: { ...devices["Desktop Safari"] },
    },
    {
      name: "mobile",
      testIgnore: /fullstack\/.*\.spec\.ts/,
      use: { ...devices["Pixel 5"] },
    },
    {
      name: "mobile-safari",
      testIgnore: /fullstack\/.*\.spec\.ts/,
      use: { ...devices["iPhone 13"] },
    },
    {
      name: "fullstack",
      testMatch: /fullstack\/.*\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        baseURL: process.env.FULLSTACK_BASE_URL || "http://127.0.0.1:3010",
        trace: "retain-on-failure",
      },
    },
  ],
  webServer: isFullstackRun
    ? undefined
    : {
        command: process.env.PLAYWRIGHT_START_CMD || "npm.cmd run start",
        url: process.env.PLAYWRIGHT_TEST_BASE_URL || "http://127.0.0.1:3000",
        reuseExistingServer: true,
        timeout: 60 * 1000,
      },
});
