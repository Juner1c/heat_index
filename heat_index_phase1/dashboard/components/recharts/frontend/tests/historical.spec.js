import { test, expect } from "@playwright/test";
import path from "node:path";

test("Himawari dashboard renders Recharts, missing hours, records, and refresh", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Historical Data Dashboard" })).toBeVisible();
  await expect(page.locator('[data-testid="stMetricValue"]').first()).toHaveText("262");
  const chart = page.frameLocator('iframe[title="components.recharts.thermocast_recharts"]').first();
  await expect(chart.locator(".recharts-line-curve")).toHaveCount(4);
  await expect(chart.getByText("Brightness temperature (K) · UTC")).toBeVisible();
  const firstPath = chart.locator(".recharts-line-curve").first();
  const pathData = await firstPath.getAttribute("d");
  expect(pathData.match(/M/g)?.length).toBe(3);
  await chart.locator(".recharts-wrapper").hover({ position: { x: 300, y: 150 } });
  await expect(chart.locator(".recharts-tooltip-wrapper")).toBeVisible();
  await chart.locator(".recharts-legend-item").first().click();
  await expect(chart.locator(".recharts-line-curve")).toHaveCount(3);
  await page.getByRole("tab", { name: "Timestamp gaps" }).click();
  await expect(page.getByText("Exact missing timestamps", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Column quality" }).click();
  await expect(page.getByText(/Detected roles:/)).toBeVisible();
  await page.getByRole("tab", { name: "Records", exact: true }).click();
  await expect(page.getByRole("button", { name: "Download displayed records" })).toBeVisible();
  await page.getByRole("button", { name: "Refresh dataset" }).click();
  await expect(page.locator('[data-testid="stMetricValue"]').first()).toHaveText("262");
  await page.getByRole("tab", { name: "Measurement history" }).click();
  await chart.locator(".recharts-legend-item").first().click();
  await expect(chart.locator(".recharts-line-curve")).toHaveCount(4);
  await page.locator('[data-testid="stMain"]').evaluate((element) => { element.scrollTop = 0; });
  await page.screenshot({ path: path.resolve("../../../../.runtime/historical-desktop.png"), fullPage: true });
  expect(errors).toEqual([]);
});

test("Recharts stays visible on a narrow display", async ({ page }) => {
  await page.setViewportSize({ width: 430, height: 932 });
  await page.goto("/");
  const chart = page.frameLocator('iframe[title="components.recharts.thermocast_recharts"]').first();
  await expect(chart.locator(".recharts-surface").first()).toBeVisible();
  const size = await chart.locator(".chart-container").boundingBox();
  expect(size.width).toBeLessThanOrEqual(430);
  expect(size.width).toBeGreaterThan(150);
  const note = chart.locator(".chart-note");
  const noteBottom = await note.evaluate((element) => element.getBoundingClientRect().bottom);
  const frameHeight = await page.locator('iframe[title="components.recharts.thermocast_recharts"]').first().evaluate((element) => element.clientHeight);
  expect(noteBottom).toBeLessThanOrEqual(frameHeight);
});

test("A chart with all legend series hidden offers one-click recovery", async ({ page }) => {
  await page.goto("/");
  const chart = page.frameLocator('iframe[title="components.recharts.thermocast_recharts"]').first();
  await expect(chart.locator(".recharts-line-curve")).toHaveCount(4);
  for (let index = 0; index < 4; index += 1) {
    await chart.locator(".recharts-legend-item").nth(index).click();
  }
  await expect(chart.getByText("All chart series are hidden.")).toBeVisible();
  await chart.getByRole("button", { name: "Show all series" }).click();
  await expect(chart.locator(".recharts-line-curve")).toHaveCount(4);
  await expect(chart.getByText("All chart series are hidden.")).toHaveCount(0);
});
