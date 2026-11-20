import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

test("analytics shell exposes the redesigned navigation and dataset context", async ({
  page,
}) => {
  await page.goto("/");

  await expect(
    page.getByRole("button", { name: "ForecastIQ home" }),
  ).toBeVisible();
  await expect(page.getByText("Forecasting", { exact: true })).toBeVisible();
  await expect(page.getByText("Inventory", { exact: true })).toBeVisible();
  await expect(page.getByText("Drag and drop or browse files")).toBeVisible();

  await page.getByRole("button", { name: /Use Demo Dataset/ }).click();
  await expect(
    page.getByRole("heading", { name: "Data quality report" }),
  ).toBeVisible();
  await expect(
    page.getByRole("banner").getByText("Retail demo dataset", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("PASS", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Demand overview" }),
  ).toBeVisible();
  await expect(
    page.getByText("Sales over time", { exact: true }),
  ).toBeVisible();
  const evidence = process.env.REDESIGN_EVIDENCE_DIR;
  if (evidence) {
    await mkdir(evidence, { recursive: true });
    await page.screenshot({
      path: `${evidence}/overview-desktop.png`,
      fullPage: true,
      animations: "disabled",
    });
  }
});

test("mobile shell opens and closes the grouped navigation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.locator(".sidebar")).toHaveClass(/open/);
  await expect(page.getByText("Forecasting", { exact: true })).toBeVisible();
  const evidence = process.env.REDESIGN_EVIDENCE_DIR;
  if (evidence) {
    await mkdir(evidence, { recursive: true });
    await page.screenshot({
      path: `${evidence}/mobile-navigation.png`,
      fullPage: true,
      animations: "disabled",
    });
  }
  await page
    .getByRole("button", { name: "Close navigation" })
    .click({ position: { x: 380, y: 20 } });
  await expect(page.locator(".sidebar")).not.toHaveClass(/open/);
});

test("inventory without a probabilistic forecast shows one actionable empty panel", async ({
  page,
}) => {
  await page.route("**/api/forecast/models?**", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Use Demo Dataset/ }).click();
  await page
    .getByRole("button", { name: "Inventory optimization", exact: true })
    .click();

  await expect(
    page.getByRole("heading", {
      name: "Inventory metrics are waiting for a probabilistic forecast.",
    }),
  ).toBeVisible();
  await expect(page.getByText("Unavailable", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Replenishment queue" }),
  ).toHaveCount(0);
  const evidence = process.env.REDESIGN_EVIDENCE_DIR;
  if (evidence) {
    await mkdir(evidence, { recursive: true });
    await page.screenshot({
      path: `${evidence}/inventory-empty.png`,
      fullPage: true,
      animations: "disabled",
    });
  }

  await page.getByRole("button", { name: "Open Advanced Forecasting" }).click();
  await expect(
    page.getByRole("heading", { name: "Forecast quality lab" }),
  ).toBeVisible();
});
