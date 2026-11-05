import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import type { AdvancedRun } from "../src/advancedTypes";
import { advancedNames } from "../src/advancedTypes";

async function train(page: Page): Promise<AdvancedRun> {
  const pending = page.waitForResponse(
    (r) => r.url().endsWith("/api/forecast/train") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Train & forecast", exact: true }).click();
  const response = await pending;
  expect(response.status(), await response.text()).toBe(201);
  const result = (await response.json()) as AdvancedRun;
  await expect(page.locator(".champion-name")).toHaveText(advancedNames[result.champion_model]);
  return result;
}

async function screenshot(page: Page, name: string) {
  if (!process.env.CAPTURE_SCREENSHOTS) return;
  await mkdir("../docs/screenshots", { recursive: true });
  await page.screenshot({ path: `../docs/screenshots/${name}.png`, fullPage: true, animations: "disabled" });
}

test("advanced training, measured quantiles, SHAP, export, independent series and saved runs", async ({ page }) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: /Use Demo Dataset/ }).click();
  await expect(page.getByRole("heading", { name: "Data quality report" })).toBeVisible();
  await page.getByRole("button", { name: "Advanced forecasting", exact: true }).click();
  await page.getByLabel("Forecast horizon (periods)").fill("7");
  await page.getByText("Evaluation options", { exact: true }).click();
  await page.getByLabel("Backtest folds").fill("2");
  const first = await train(page);
  expect(first.forecast).toHaveLength(7);
  expect(first.comparison).toHaveLength(10);
  expect(first.comparison.find((r) => r.model === "nbeats")?.status).toBe("skipped");
  expect(first.comparison.filter((r) => r.status === "ok")).toHaveLength(9);
  await expect(page.locator(".advanced-comparison tbody tr")).toHaveCount(10);
  await expect(page.locator(".champion-row")).toContainText(advancedNames[first.champion_model]);
  await expect(page.locator(".stats-grid").first()).toContainText(`${(first.test_metrics.wape! * 100).toFixed(2)}%`);
  await expect(page.locator(".forecast-table-scroll tbody tr")).toHaveCount(7);
  for (const point of first.forecast) {
    expect(point.p10).toBeLessThanOrEqual(point.p50);
    expect(point.p50).toBeLessThanOrEqual(point.p90);
  }
  // The interval is an actual SVG area, not just a legend or a table.
  await expect(page.getByRole("img", { name: "P50 forecast and P10 to P90 uncertainty band" }).locator(".recharts-area-area")).toHaveAttribute("d", /.+/);
  await page.getByLabel("Comparison statistic").selectOption("std");
  await expect(page.locator(".champion-row")).toContainText(`${(first.comparison.find((r) => r.model === first.champion_model)!.summary!.wape.std! * 100).toFixed(2)}%`);
  await page.getByLabel("Comparison statistic").selectOption("mean");
  await page.getByLabel("Backtest fold", { exact: true }).selectOption("1");
  await expect(page.getByRole("img", { name: "Backtest actual and predicted demand" })).toBeVisible();
  await page.getByLabel("Explainability model").selectOption("xgboost");
  await expect(page.locator(".importance-list > div")).toHaveCount(10);
  const drivers = first.explainability.xgboost.forecast_drivers[0];
  await expect(page.locator(".driver-list")).toContainText(drivers.drivers[0].feature);
  expect(drivers.base_value + drivers.drivers.reduce((sum, d) => sum + d.shap_value, 0)).toBeCloseTo(drivers.raw_prediction, 3);
  await page.getByLabel("Explain forecast date").selectOption("1");
  await page.getByLabel("SHAP summary feature").selectOption("rolling_mean_28");
  await expect(page.locator(".shap-summary .recharts-scatter-symbol")).toHaveCount(40);
  const downloadPending = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export forecast CSV" }).click();
  const download = await downloadPending;
  expect(download.suggestedFilename()).toBe(`forecast-${first.run_id}.csv`);
  const csv = await page.request.get(`/api/forecast/export/${first.run_id}`);
  expect((await csv.text()).trim().split("\n")).toHaveLength(8);
  await page.getByText("Evaluation options", { exact: true }).click();
  await screenshot(page, "phase2-forecast-quality");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await screenshot(page, "phase2-mobile");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByLabel("Advanced store").selectOption("STORE_02");
  const second = await train(page);
  expect(second.store_id).toBe("STORE_02");
  expect(second.run_id).not.toBe(first.run_id);
  await page.getByLabel("Series to compare").selectOption(JSON.stringify([first.store_id, first.product_id]));
  await page.getByRole("button", { name: "Compare series", exact: true }).click();
  const seriesPanel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Compare independent series" }) });
  await expect(seriesPanel.locator("tbody tr")).toHaveCount(2);
  await expect(seriesPanel).toContainText("STORE_01 / SKU_001");
  await expect(seriesPanel).not.toContainText("Train this series first");
  await page.getByLabel("Saved training run").selectOption(first.run_id);
  await expect(page.getByLabel("Advanced store")).toHaveValue("STORE_01");
  await page.reload();
  await page.getByRole("button", { name: "Advanced forecasting", exact: true }).click();
  await expect(page.getByLabel("Saved training run")).toHaveValue(first.run_id);
  await expect(page.locator(".champion-name")).toHaveText(advancedNames[first.champion_model]);
  expect(errors).toEqual([]);
});

test("mapped target and time columns support monthly forecasting through the UI", async ({ page }) => {
  test.setTimeout(120_000);
  const rows = ["period,demand,shop,sku_id,price"];
  for (let i = 0; i < 120; i++) {
    const date = new Date(Date.UTC(2015, i, 1)).toISOString().slice(0, 10);
    rows.push(`${date},${40 + (i % 12) * 2 + Math.floor(i / 24)},001,002,9.5`);
  }
  await page.goto("/");
  await page.getByText("Column names and frequency for your CSV", { exact: true }).click();
  await page.getByLabel("Time column", { exact: true }).fill("period");
  await page.getByLabel("Demand / target column", { exact: true }).fill("demand");
  await page.getByLabel("Store column", { exact: true }).fill("shop");
  await page.getByLabel("Upload frequency").selectOption("monthly");
  await page.getByLabel("Upload sales CSV").setInputFiles({ name: "monthly-demand.csv", mimeType: "text/csv", buffer: Buffer.from(rows.join("\n")) });
  await expect(page.getByRole("heading", { name: "Data quality report" })).toBeVisible();
  await expect(page.locator(".check-list")).toContainText("MS");
  await page.getByRole("button", { name: "Advanced forecasting", exact: true }).click();
  await expect(page.getByLabel("Advanced store")).toHaveValue("001");
  await expect(page.getByLabel("Advanced product")).toHaveValue("002");
  await page.getByLabel("Forecast horizon (periods)").fill("7");
  await page.getByText("Evaluation options", { exact: true }).click();
  await page.getByLabel("Backtest folds").fill("2");
  const run = await train(page);
  expect(run.frequency).toBe("MS");
  expect(run.forecast[0].date).toBe("2025-01-01");
  expect(run.forecast[6].date).toBe("2025-07-01");
  await expect(page.locator(".forecast-table-scroll tbody tr")).toHaveCount(7);
  await screenshot(page, "phase2-monthly");
});
