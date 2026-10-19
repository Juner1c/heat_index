import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { mockIoT, latest, history, unavailable } from "./fixtures/iot";

test("Live IoT cards, unverified timestamps, Recharts, and forecast separation", async ({page}) => {
  await mockIoT(page);
  await page.goto("/");
  const panel=page.locator(".iot-panel");
  await expect(panel.getByRole("heading",{name:"Live IoT Weather"})).toBeVisible();
  await expect(panel.getByText("31.2 °C",{exact:true})).toBeVisible();
  await expect(panel.getByText("Sensor freshness: unknown")).toBeVisible();
  await expect(panel.getByText(/date and timezone unknown/)).toBeVisible();
  await page.goto("/weather");
  await expect(page.locator(".iot-charts .recharts-line-curve")).toHaveCount(3);
  await expect(page.locator(".iot-charts").getByText(/categorical, not elapsed time/)).toBeVisible();
  await expect(page.getByText("Experimental IoT forecast — unvalidated:",{exact:true})).toBeVisible();
  await expect(page.getByText(/Data source: open_meteo_clean.csv/)).toBeVisible();
  await page.screenshot({path:path.resolve("../.runtime/iot-weather-mocked.png"),fullPage:true});
  await page.goto("/heat-index");
  await expect(page.getByRole("heading",{name:"Historical heat index",exact:true})).toBeVisible();
  await expect(page.locator(".iot-panel .recharts-line-curve")).toHaveCount(0);
  await expect(page.getByText("37.4 °C",{exact:true})).toBeVisible();
  await page.goto("/forecasting");
  await expect(page.locator(".iot-panel")).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Generate forecast",exact:true})).toBeEnabled();
});

test("Historical source selection preserves raw IoT times and exports bounded CSV",async({page})=>{
  await mockIoT(page);
  await page.goto("/historical");
  await page.getByLabel("Historical data source").selectOption("iot");
  await expect(page.getByRole("heading",{name:"IoT sensor historical readings"})).toBeVisible();
  await expect(page.locator(".iot-panel tbody tr")).toHaveCount(3);
  await expect(page.locator(".iot-panel tbody tr").first()).toContainText("2024-01-01 12:34:56");
  await expect(page.locator(".iot-panel tbody tr").first()).toContainText("timezone unverified");
  const downloadEvent=page.waitForEvent("download");
  await page.getByRole("button",{name:"Export sensor CSV"}).click();
  const download=await downloadEvent;
  expect(download.suggestedFilename()).toBe("iot_sensor_history.csv");
  const csv=await readFile(await download.path(),"utf8");
  expect(csv).toContain('"2024-01-01 12:34:56","","timezone_unverified"');
  await page.getByLabel("Historical data source").selectOption("weather");
  await expect(page.getByRole("heading",{name:"Ground-weather history",exact:true})).toBeVisible();
  await page.getByLabel("Historical data source").selectOption("satellite");
  await expect(page.getByRole("heading",{name:"Historical records",exact:true})).toBeVisible();
});

test("IoT quality and unreachable or empty sensor states remain explicit",async({page})=>{
  await mockIoT(page, latest, {...history, invalid_readings:1,invalid_fields:2});
  await page.goto("/quality");
  await expect(page.getByRole("heading",{name:"IoT data quality"})).toBeVisible();
  await expect(page.locator(".iot-panel").getByText("Sensor freshness: unknown")).toBeVisible();
  await expect(page.locator(".iot-panel").getByText(/missing time intervals cannot be quantified/)).toBeVisible();
  await mockIoT(page,unavailable,unavailable);
  await page.goto("/weather");
  await expect(page.locator(".iot-panel").getByText("Server unavailable",{exact:true})).toBeVisible();
  await expect(page.locator(".iot-panel .stat-card strong")).toHaveText(["—","—","—"]);
  await expect(page.locator(".iot-charts .recharts-line-curve")).toHaveCount(0);
  await mockIoT(page,latest,{...history,status:"no_data",records:[],returned_count:0});
  await page.reload();
  await expect(page.getByText("No sensor history is available.",{exact:true})).toBeVisible();
});

test("Polling waits for the whole request batch and is cleaned up on unmount",async({page})=>{
  await page.clock.install();
  let latestCalls=0,historyCalls=0,releaseHistory;
  const gate=new Promise((resolve)=>{releaseHistory=resolve;});
  await page.route("**/api/iot/latest",async(route)=>{latestCalls++;await route.fulfill({contentType:"application/json",body:JSON.stringify(latest)});});
  await page.route("**/api/iot/history**",async(route)=>{historyCalls++;if(historyCalls===1)await gate;await route.fulfill({contentType:"application/json",body:JSON.stringify(history)});});
  await page.goto("/weather");
  await expect.poll(()=>historyCalls).toBe(1);
  const first=latestCalls;
  await page.clock.fastForward(20000);
  expect(latestCalls).toBe(first);expect(historyCalls).toBe(1);
  releaseHistory();
  await expect(page.locator(".iot-charts .recharts-line-curve")).toHaveCount(3);
  await page.clock.fastForward(10001);
  await expect.poll(()=>latestCalls).toBe(first+1);
  await expect.poll(()=>historyCalls).toBe(2);
  // Navigate within React so this verifies hook unmount, not just browser reload.
  await page.getByRole("link",{name:/AI Forecasting/}).click();
  await expect(page.getByRole("button",{name:"Generate forecast",exact:true})).toBeVisible();
  const stopped=latestCalls;
  await page.clock.fastForward(30000);
  expect(latestCalls).toBe(stopped);
});

test("IoT history charts and controls remain responsive",async({page})=>{
  await mockIoT(page);
  for(const width of [390,768,1024]){
    await page.setViewportSize({width,height:1000});
    await page.goto("/weather");
    await expect(page.locator(".iot-charts .recharts-line-curve")).toHaveCount(3);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
});
