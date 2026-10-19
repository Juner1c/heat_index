import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 45000,
  expect: { timeout: 20000 },
  workers: 1,
  use: {
    baseURL: process.env.DASHBOARD_URL || "http://127.0.0.1:8501",
    browserName: "chromium",
    channel: process.env.PLAYWRIGHT_CHANNEL || "msedge",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
});
