import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";

async function screenshot(page: Page, name: string) {
  if (!process.env.CAPTURE_SCREENSHOTS) return;
  await mkdir("../docs/screenshots", { recursive: true });
  await page.screenshot({
    path: `../docs/screenshots/${name}.png`,
    fullPage: true,
    animations: "disabled",
  });
}

test("demo → quality → analytics → measured forecast → model comparison", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Know your demand/ }),
  ).toBeVisible();
  await screenshot(page, "welcome");
  await page.getByRole("button", { name: /Use Demo Dataset/ }).click();
  await expect(
    page.getByRole("heading", { name: "Data quality report" }),
  ).toBeVisible();
  await expect(page.getByText("4,380", { exact: true })).toBeVisible();
  await screenshot(page, "data-quality");
  await page.getByRole("button", { name: "Explore dashboard" }).click();
  await expect(
    page.getByRole("heading", { name: "Sales over time" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Monthly seasonality" }),
  ).toBeVisible();
  await screenshot(page, "dashboard");
  await page.getByLabel("Store", { exact: true }).selectOption("STORE_02");
  await page.getByLabel("Product", { exact: true }).selectOption("SKU_003");
  await expect(
    page.locator(".stats-grid").getByText("1 / 1", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Create a forecast" }).click();
  await page.getByLabel("Store", { exact: true }).selectOption("STORE_01");
  await page.getByLabel("Product", { exact: true }).selectOption("SKU_001");
  const responsePromise = page.waitForResponse(
    (r) => r.url().endsWith("/api/forecast") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate forecast" }).click();
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  const forecast = await response.json();
  expect(forecast.forecast).toHaveLength(28);
  await expect(page.getByText("28-DAY DEMAND FORECAST")).toBeVisible();
  await expect(page.locator(".forecast-total")).toContainText(
    Math.round(forecast.summary.forecast_total).toLocaleString("en-US"),
  );
  await expect(
    page.getByRole("heading", { name: "Inventory gap", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".metric-grid")).toContainText(
    `${(forecast.test_metrics.wape * 100).toFixed(2)}%`,
  );
  await screenshot(page, "forecast");
  await page
    .getByRole("button", { name: "View model comparison" })
    .first()
    .click();
  await expect(page.locator(".comparison-table tbody tr")).toHaveCount(4);
  await expect(page.locator(".comparison-table")).toContainText(
    "Linear regression",
  );
  await screenshot(page, "model-comparison");
  await page.getByRole("button", { name: "Final test", exact: true }).click();
  await expect(page.locator(".comparison-table")).toContainText(
    `${(forecast.test_metrics.wape * 100).toFixed(2)}%`,
  );
  await page.getByRole("button", { name: "Back to forecast" }).click();
  for (const horizon of [7, 14]) {
    await page
      .getByRole("button", { name: `${horizon} days`, exact: true })
      .click();
    await expect(page.locator(".forecast-total")).toHaveCount(0);
    await page.getByRole("button", { name: "Generate forecast" }).click();
    await expect(
      page.getByText(`${horizon}-DAY DEMAND FORECAST`),
    ).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("invalid CSV shows an error and valid upload enables forecasting", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Upload sales CSV").setInputFiles({
    name: "invalid.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("date,store_id\n2025-01-01,S1"),
  });
  await expect(page.getByRole("alert")).toContainText(
    "Missing required columns",
  );
  await page
    .getByLabel("Upload sales CSV")
    .setInputFiles(path.resolve("../data/demo/retail_sales.csv"));
  await expect(
    page.getByRole("heading", { name: "Data quality report" }),
  ).toBeVisible();
  await expect(page.locator(".dataset-pill")).toContainText("Uploaded dataset");
  await page
    .getByRole("button", { name: "Demand forecast", exact: true })
    .click();
  await page.getByRole("button", { name: "7 days", exact: true }).click();
  await page.getByRole("button", { name: "Generate forecast" }).click();
  await expect(page.getByText("7-DAY DEMAND FORECAST")).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Demand overview" }),
  ).toBeVisible();
});

test("mobile layout supports navigation and forecasting without horizontal overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: /Use Demo Dataset/ }).click();
  await page.getByRole("button", { name: "Explore dashboard" }).click();
  await expect(
    page.getByRole("heading", { name: "Sales over time" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("button", { name: "Demand forecast", exact: true })
    .click();
  await page.getByRole("button", { name: "Generate forecast" }).click();
  await expect(page.getByText("28-DAY DEMAND FORECAST")).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflow).toBe(false);
  await screenshot(page, "forecast-mobile");
});

test("explicit zero policy stays visible when returning to a saved forecast", async ({
  page,
}) => {
  const lines = (await readFile("../data/demo/retail_sales.csv", "utf8")).split(
    "\n",
  );
  lines.splice(31, 1);
  await page.goto("/");
  await page.getByLabel("Upload sales CSV").setInputFiles({
    name: "with-gap.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(lines.join("\n")),
  });
  await expect(
    page.getByRole("heading", { name: "Data quality report" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Demand forecast", exact: true })
    .click();
  const consent = page.getByRole("checkbox", {
    name: /I confirm that missing observations/,
  });
  await consent.check();
  await page.getByRole("button", { name: "Generate forecast" }).click();
  await expect(page.getByText("28-DAY DEMAND FORECAST")).toBeVisible();
  await expect(
    page.getByText(/Explicit zero policy applied to 1 missing/),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "View model comparison" })
    .first()
    .click();
  await page.getByRole("button", { name: "Back to forecast" }).click();
  await expect(consent).toBeChecked();
});

test("leaving the forecast page discards an in-flight result", async ({
  page,
}) => {
  let signalReady!: () => void;
  let releaseResponse!: () => void;
  let signalHandled!: () => void;
  const ready = new Promise<void>((resolve) => {
    signalReady = resolve;
  });
  const gate = new Promise<void>((resolve) => {
    releaseResponse = resolve;
  });
  const handled = new Promise<void>((resolve) => {
    signalHandled = resolve;
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Use Demo Dataset/ }).click();
  await page
    .getByRole("button", { name: "Demand forecast", exact: true })
    .click();
  await page.route("**/api/forecast", async (route) => {
    const response = await route.fetch();
    signalReady();
    await gate;
    await route.fulfill({ response }).catch(() => {
      /* The browser may already have aborted. */
    });
    signalHandled();
  });
  await page.getByRole("button", { name: "Generate forecast" }).click();
  await ready;
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  releaseResponse();
  await handled;
  await page
    .getByRole("button", { name: "Model comparison", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Every comparison starts with a forecast",
    }),
  ).toBeVisible();
});
