import { test, expect } from "@playwright/test";
import path from "node:path";
import { mockIoT, unavailable } from "./fixtures/iot";

// Keep existing regressions deterministic and independent of the external IoT server.
test.beforeEach(async ({ page }) => { await mockIoT(page, unavailable, unavailable); });

test("All six pages use real datasets and forecasting readiness is explicit", async ({ page, request }) => {
  const errors = []; page.on("pageerror", (error) => errors.push(error.message));
  const summary = await (await request.get("http://127.0.0.1:8000/api/himawari/summary")).json();
  await page.goto("/");
  await expect(page.locator(".stat-card").first().locator("strong")).toHaveText(summary.total_records.toLocaleString("en-US"));
  await expect(page.locator(".recharts-line-curve")).toHaveCount(summary.bands.length);
  await page.screenshot({ path: path.resolve("../.runtime/phase2-overview.png"), fullPage: true });
  await page.getByRole("link", { name: "Historical Data", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Historical records" })).toBeVisible();
  await page.getByLabel("Band statistic").selectOption("all");
  await expect(page.locator(".recharts-line-curve")).toHaveCount(summary.bands.length * 3);
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.locator(".pagination")).toContainText("Page 2 of");
  await page.getByLabel("From date").fill("2024-08-01"); await page.getByLabel("Through date").fill("2024-08-01");
  await page.getByRole("button", { name: "Apply range" }).click();
  await expect(page.locator(".pagination")).toContainText("Page 1 of 1");
  const downloadEvent = page.waitForEvent("download"); await page.getByRole("button", { name: "Export CSV", exact: true }).click();
  expect((await downloadEvent).suggestedFilename()).toBe("himawari_history.csv");
  await page.getByRole("link", { name: "Weather Monitoring", exact: true }).click();
  await expect(page.getByText("Data source: open_meteo_clean.csv · UTC", { exact: false })).toBeVisible();
  await expect(page.locator(".recharts-line-curve")).toHaveCount(2);
  await page.getByRole("link", { name: "Heat Index Analysis", exact: true }).click();
  await expect(page.locator(".recharts-line-curve")).toHaveCount(1);
  await page.getByText("Calculation method & data provenance").click();
  await expect(page.getByText(/Stored heat_index_C from/)).toBeVisible();
  await page.getByRole("link", { name: /AI Forecasting/ }).click();
  await expect(page.getByRole("button", { name: "Generate forecast", exact: true })).toBeVisible();
  await expect(page.locator(".recharts-line-curve")).toHaveCount(0);
  await page.getByRole("link", { name: "Data Quality", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Existing coverage reports" })).toBeVisible();
  await page.getByRole("button", { name: "Refresh data" }).click();
  await expect(page.getByRole("button", { name: "Missing-hour report" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("Original-model forecast shows timestamped output, loading, and errors", async ({ page }) => {
  await page.goto("/forecasting");
  const button = page.getByRole("button", { name: "Generate forecast", exact: true });
  await expect(button).toBeEnabled();
  const [response] = await Promise.all([page.waitForResponse((result) => result.url().includes("/api/forecast/predict") && result.request().method() === "POST"), button.click()]);
  const result = await response.json();
  expect(response.status()).toBe(200);
  expect(Date.parse(result.predictions[0].timestamp) - Date.parse(result.last_input_observation)).toBe(3600000);
  await expect(page.getByText("Historical-origin forecast · research prototype", { exact: true })).toBeVisible();
  await expect(page.locator(".recharts-line-dot")).toHaveCount(1);
  await page.screenshot({ path: path.resolve("../.runtime/phase3-forecast.png"), fullPage: true });
  await page.route("**/api/forecast/predict", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 700));
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: { code: "model_unavailable", message: "The checkpoint is unavailable." } }) });
  });
  await button.click();
  await expect(page.getByRole("button", { name: "Generating forecast…", exact: true })).toBeDisabled();
  await expect(page.getByRole("alert")).toContainText("The checkpoint is unavailable.");
});

test("Unavailable models disable the prediction button with a clear explanation", async ({ page }) => {
  await page.route("**/api/models/status", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ inference_ready: false, models: [{ identifier: "sequence_time_constant", inference_ready: false, message: "Saved scalers are missing." }] }) }));
  await page.goto("/forecasting");
  await expect(page.getByRole("button", { name: "Generate forecast", exact: true })).toBeDisabled();
  await expect(page.getByText("Saved scalers are missing.")).toBeVisible();
});

test("Mobile navigation and missing-file states remain usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator(".stat-card").first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("link", { name: "Weather Monitoring", exact: true }).click();
  await page.route("**/api/weather/history**", (route) => route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: { code: "source_missing", message: "The weather dataset is unavailable." } }) }));
  await page.getByRole("button", { name: "Refresh data" }).click();
  await expect(page.getByRole("alert").first()).toContainText("The weather dataset is unavailable.");
  await page.screenshot({ path: path.resolve("../.runtime/phase2-mobile.png"), fullPage: true });
});

test("Tablet layouts keep navigation and charts inside the viewport", async ({ page }) => {
  for (const width of [1024, 768]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/historical");
    await expect(page.locator(".recharts-line-curve")).toHaveCount(4);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await expect(page.getByRole("link", { name: "Data Quality", exact: true })).toBeVisible();
    await page.goto("/forecasting");
    await expect(page.getByRole("button", { name: "Generate forecast", exact: true })).toBeEnabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
});
