import { expect, test, type Page } from "@playwright/test";

async function setup(page: Page) {
  const dataset = await (await page.request.post("/api/datasets/demo")).json();
  const response = await page.request.post("/api/forecast/train", {
    data: {
      dataset_id: dataset.dataset_id,
      store_id: "STORE_01",
      product_id: "SKU_001",
      horizon: 30,
      folds: 2,
      models: ["naive", "seasonal_naive"],
    },
  });
  expect(response.status()).toBe(201);
  const run = await response.json();
  await page.goto("/");
  await page.evaluate(
    (id) => localStorage.setItem("forecastiq.dataset", id),
    dataset.dataset_id,
  );
  await page.reload();
  await page
    .getByRole("button", { name: "Inventory optimization", exact: true })
    .click();
  await expect(page.getByLabel("Inventory forecast")).toHaveValue(run.run_id);
  return run;
}

test("late receipts require expediting without duplicating purchase orders", async ({
  page,
}) => {
  await setup(page);
  await page.getByLabel("On-hand inventory", { exact: true }).fill("0");
  await page.getByLabel("On-order inventory", { exact: true }).fill("100000");
  await page.getByLabel("Lead time (periods)", { exact: true }).fill("2");
  await page
    .getByText("Costs, supply arrivals and forecast uncertainty", {
      exact: true,
    })
    .click();
  await page
    .getByLabel("Incoming orders", { exact: true })
    .fill('[{"period":20,"quantity":100000}]');
  const calculated = page.waitForResponse((r) =>
    r.url().endsWith("/inventory/optimize"),
  );
  await page
    .getByRole("button", { name: "Calculate replenishment", exact: true })
    .click();
  const plan = await (await calculated).json();
  expect(plan.risk_level).toBe("high");
  expect(plan.recommended_order_quantity).toBe(0);
  expect(plan.expedite_quantity).toBeGreaterThan(0);
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Expedite or reschedule supply" }),
  ).toBeVisible();
  await expect(page.getByText("Expedite units", { exact: true })).toBeVisible();
  await page.getByLabel("Simulation mode").selectOption("deterministic");
  await page.getByLabel("Simulation horizon", { exact: true }).fill("7");
  const simulated = page.waitForResponse((r) =>
    r.url().endsWith("/inventory/simulate"),
  );
  await page
    .getByRole("button", { name: "Run simulation", exact: true })
    .click();
  expect((await (await simulated).json()).fill_rate).toBe(0);
  await page
    .getByLabel("Incoming orders", { exact: true })
    .fill('[{"period":1,"quantity":100000}]');
  const recalculated = page.waitForResponse((r) =>
    r.url().endsWith("/inventory/optimize"),
  );
  await page
    .getByRole("button", { name: "Calculate replenishment", exact: true })
    .click();
  expect((await (await recalculated).json()).risk_level).toBe("low");
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Expedite or reschedule supply" }),
  ).toHaveCount(0);
});

test("inventory forecast selector fetches beyond the first catalog page", async ({
  page,
}) => {
  const run = await setup(page);
  const response = await page.request.get(
    `/api/forecast/models?dataset_id=${run.dataset_id}`,
  );
  const saved = (await response.json())[0];
  // Exercise pagination in the browser independently of costly catalog training.
  const rows = Array.from({ length: 101 }, (_, i) => ({
    ...saved,
    run_id: i === 0 ? run.run_id : `catalog-run-${i}`,
  }));
  const offsets: number[] = [];
  await page.route("**/api/forecast/models?**", async (route) => {
    const offset = Number(
      new URL(route.request().url()).searchParams.get("offset") ?? 0,
    );
    offsets.push(offset);
    await route.fulfill({ json: rows.slice(offset, offset + 100) });
  });
  await page.goto(`/?dataset=${run.dataset_id}&view=inventory`);
  await expect(
    page.getByLabel("Inventory forecast").locator("option"),
  ).toHaveCount(101);
  expect(offsets).toEqual([0, 100]);
  await expect(
    page
      .getByLabel("Inventory forecast")
      .locator('option[value="catalog-run-100"]'),
  ).toHaveCount(1);
});

test("saved plans without receipt checks request recalculation", async ({
  page,
}) => {
  const run = await setup(page);
  const result = await page.request.post("/api/inventory/optimize", {
    data: {
      forecast_run_id: run.run_id,
      on_hand_inventory: 100000,
      lead_time: 2,
    },
  });
  const plan = await result.json();
  await page.route(`**/api/inventory/plans/${plan.plan_id}`, async (route) => {
    const saved = await (await route.fetch()).json();
    delete saved.supply_timing_note;
    delete saved.expedite_quantity;
    delete saved.expedite_needed;
    await route.fulfill({ json: saved });
  });
  await page.goto(
    `/?dataset=${run.dataset_id}&view=inventory&plan=${plan.plan_id}`,
  );
  await expect(page.getByText(/This saved plan predates/)).toBeVisible();
  await expect(
    page.getByText("RECALCULATE RISK", { exact: true }),
  ).toBeVisible();
});

test("forecast to replenishment, simulations, policies, what-if and CSV export", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const run = await setup(page);
  const training: string[] = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/forecast/train")) training.push(r.url());
  });
  await page.getByLabel("On-hand inventory", { exact: true }).fill("150");
  await page.getByLabel("Lead time (periods)", { exact: true }).fill("7");
  await page
    .getByText("Costs, supply arrivals and forecast uncertainty", {
      exact: true,
    })
    .click();
  await page.getByLabel("Annual demand", { exact: true }).fill("12000");
  await page.getByLabel("Cost per order", { exact: true }).fill("20");
  await page
    .getByLabel("Annual holding cost / unit", { exact: true })
    .fill("3");
  await page.getByLabel("Shortage cost / unit", { exact: true }).fill("8");
  await page.getByLabel("Unit cost", { exact: true }).fill("12");
  await page.getByLabel("Currency", { exact: true }).fill("USD");
  const calculated = page.waitForResponse((r) =>
    r.url().endsWith("/inventory/optimize"),
  );
  await page
    .getByRole("button", { name: "Calculate replenishment", exact: true })
    .click();
  const plan = await (await calculated).json();
  expect(plan.expected_lead_time_demand).toBeCloseTo(
    run.forecast
      .slice(0, 7)
      .reduce((s: number, p: { p50: number }) => s + p.p50, 0),
  );
  expect(plan.eoq).toBe(400);
  await expect(
    page.getByRole("heading", { name: /2. Replenishment decision/ }),
  ).toBeVisible();
  await page.getByLabel("Simulation mode").selectOption("deterministic");
  await page
    .getByRole("button", { name: "Run simulation", exact: true })
    .click();
  await expect(page.getByText(/deterministic · 1 paths/)).toBeVisible();
  await page.getByLabel("Simulation mode").selectOption("monte_carlo");
  await page.getByLabel("Monte Carlo paths").selectOption("100");
  await page
    .getByRole("button", { name: "Run simulation", exact: true })
    .click();
  await expect(page.getByText(/monte_carlo · 100 paths/)).toBeVisible();
  await page.getByLabel("Minimum fill rate", { exact: true }).fill("0.5");
  await page
    .getByRole("button", { name: "Compare policies", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Policy cost / service comparison" }),
  ).toBeVisible();
  await expect(
    page.getByText("Optimized service-level policy", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Lead time (periods)", { exact: true }).fill("3");
  await expect(
    page.getByRole("button", { name: "Run simulation", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Compare inputs as what-if", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "What-if comparison", exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export CSV", exact: true }).click();
  expect((await download).suggestedFilename()).toBe(
    "inventory-recommendations.csv",
  );
  await page
    .getByRole("button", { name: "SKU_001 / STORE_01", exact: true })
    .click();
  await expect(
    page.getByLabel("Lead time (periods)", { exact: true }),
  ).toHaveValue("7");
  await expect(page.getByText(/monte_carlo · 100 paths/)).toBeVisible();
  expect(training).toHaveLength(0);
  await page.evaluate(() => localStorage.clear());
  await page.goto(
    `/?dataset=${run.dataset_id}&view=inventory&plan=${plan.plan_id}`,
  );
  await expect(
    page.getByRole("heading", { name: /2. Replenishment decision/ }),
  ).toBeVisible();
  await expect(page.getByText(/monte_carlo · 100 paths/)).toBeVisible();
  expect(errors).toHaveLength(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  if (process.env.CAPTURE_SCREENSHOTS) {
    await page.screenshot({
      path: "../docs/screenshots/phase3-inventory.png",
      fullPage: true,
    });
  }
});

test("batch CSV, risk filter, saved plan and missing costs remain explicit", async ({
  page,
}) => {
  const run = await setup(page);
  const csv = `forecast_run_id,on_hand_inventory,lead_time,warehouse_id\n${run.run_id},0,7,WEST\n${run.run_id},9999,7,EAST\nmissing,0,7,BAD\n`;
  await page.getByLabel("Import inventory CSV", { exact: true }).setInputFiles({
    name: "inventory.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await expect(page.getByText(/2 plans saved; 1 rows rejected/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "SKU_001 / EAST", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Risk filter").selectOption("high");
  await expect(
    page.getByRole("button", { name: "SKU_001 / EAST", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "SKU_001 / WEST", exact: true })
    .click();
  await expect(
    page.getByText(
      "EOQ requires annual demand, ordering cost and annual holding cost.",
      { exact: true },
    ),
  ).toBeVisible();
  await page.getByLabel("Simulation mode").selectOption("deterministic");
  await page
    .getByRole("button", { name: "Run simulation", exact: true })
    .click();
  await expect(
    page.getByText(
      "Missing annual holding cost, ordering cost, stockout cost",
      { exact: true },
    ),
  ).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: "Inventory optimization", exact: true })
    .click();
  await page
    .getByRole("button", { name: "SKU_001 / WEST", exact: true })
    .click();
  await expect(page.getByText(/deterministic · 1 paths/)).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("mobile inventory layout and uncovered lead-time validation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  // Navigate at desktop width before checking the mobile layout.
  await page.setViewportSize({ width: 1280, height: 900 });
  await setup(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel("On-hand inventory", { exact: true }).fill("0");
  await page.getByLabel("Lead time (periods)", { exact: true }).fill("90");
  await page
    .getByRole("button", { name: "Calculate replenishment", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Lead time exceeds the saved forecast horizon",
  );
  await page.getByLabel("Lead time (periods)", { exact: true }).fill("2");
  await page
    .getByRole("button", { name: "Calculate replenishment", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /2. Replenishment decision/ }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  const width = await page.evaluate(() => ({
    viewport: innerWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(width.document).toBeLessThanOrEqual(width.viewport);
  if (process.env.CAPTURE_SCREENSHOTS) {
    await page.screenshot({
      path: "../docs/screenshots/phase3-mobile.png",
      fullPage: true,
    });
  }
});
