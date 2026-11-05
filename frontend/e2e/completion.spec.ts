import { expect, test } from "@playwright/test";

test("Kaggle sales upload works with default column settings after changing datasets", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Use Demo Dataset/ }).click();
  await expect(
    page.getByRole("heading", { name: "Data quality report" }),
  ).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: "Change dataset", exact: true })
    .click();
  for (const file of [
    { name: "test.csv", csv: "id,date,store,item\n0,2025-01-01,001,002\n" },
    { name: "sample_submission.csv", csv: "id,sales\n0,52\n" },
  ]) {
    await page.getByLabel("Upload sales CSV").setInputFiles({
      name: file.name,
      mimeType: "text/csv",
      buffer: Buffer.from(file.csv),
    });
    await expect(page.getByRole("alert")).toContainText(`${file.name}:`);
    await expect(page.getByRole("alert")).toContainText("upload train.csv");
  }
  const rows = ["date,store,item,sales"];
  for (let i = 0; i < 140; i++) {
    const date = new Date(Date.UTC(2025, 0, i + 1)).toISOString().slice(0, 10);
    rows.push(`${date},001,002,${20 + (i % 7)}`);
  }
  const uploaded = page.waitForResponse((r) =>
    r.url().endsWith("/datasets/upload"),
  );
  await page.getByLabel("Upload sales CSV").setInputFiles({
    name: "train.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(rows.join("\n")),
  });
  const response = await uploaded;
  expect(response.status(), await response.text()).toBe(201);
  const dataset = await response.json();
  expect(dataset.column_mapping).toMatchObject({
    units_sold: "sales",
    store_id: "store",
    product_id: "item",
  });
  await expect(
    page.getByRole("heading", { name: "Data quality report" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Demand forecast", exact: true })
    .click();
  await page.getByRole("button", { name: "7 days", exact: true }).click();
  await page.getByRole("button", { name: "Generate forecast" }).click();
  await expect(page.getByText("7-DAY DEMAND FORECAST")).toBeVisible();
});

test("price-free custom predictors reach statistics, randomized training, SHAP and inventory", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const rows = ["period,demand,temperature"];
  for (let i = 0; i < 240; i++) {
    const date = new Date(Date.UTC(2024, 0, i + 1)).toISOString().slice(0, 10);
    rows.push(`${date},${40 + (i % 7) + Math.floor(i / 30)},${10 + (i % 30)}`);
  }
  await page.goto("/");
  await page
    .getByText("Column names and frequency for your CSV", { exact: true })
    .click();
  await page.getByLabel("Time column", { exact: true }).fill("period");
  await page
    .getByLabel("Demand / target column", { exact: true })
    .fill("demand");
  await page.getByLabel("Store column", { exact: true }).fill("__single__");
  await page
    .getByLabel("Product / SKU column", { exact: true })
    .fill("__single__");
  await page
    .getByLabel("Additional numeric predictors (comma-separated)")
    .fill("temperature");
  await page.getByLabel("Upload sales CSV").setInputFiles({
    name: "custom-demand.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(rows.join("\n")),
  });
  await expect(
    page.getByRole("heading", { name: "Data quality report" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Demand statistics" }),
  ).toBeVisible();
  await expect(page.getByText("Median demand", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Demand volatility", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Advanced forecasting", exact: true })
    .click();
  await page.getByLabel("Forecast horizon (periods)").fill("7");
  await page.getByText("Evaluation options", { exact: true }).click();
  await expect(
    page.getByText(/Selected numeric predictors: temperature/),
  ).toBeVisible();
  await page.getByLabel("Backtest folds").fill("2");
  await page.getByLabel("Tree search trials").fill("3");
  await page.getByLabel("Tree search seed").fill("17");
  const trained = page.waitForResponse((r) =>
    r.url().endsWith("/forecast/train"),
  );
  await page
    .getByRole("button", { name: "Train & forecast", exact: true })
    .click();
  const response = await trained;
  expect(response.status(), await response.text()).toBe(201);
  const run = await response.json();
  for (const name of ["lightgbm", "xgboost"]) {
    const row = run.comparison.find(
      (item: { model: string }) => item.model === name,
    );
    expect(row.status).toBe("ok");
    expect(row.trials).toHaveLength(3);
    expect(row.tuning_seed).toBe(17);
    expect(run.artifacts[name].features).toContain("temperature");
  }
  await page.getByLabel("Explainability model").selectOption("xgboost");
  await page.getByLabel("SHAP summary feature").selectOption("temperature");
  await expect(
    page.locator(".shap-summary .recharts-scatter-symbol"),
  ).toHaveCount(40);
  await page.reload();
  await page
    .getByRole("button", { name: "Advanced forecasting", exact: true })
    .click();
  await page.getByText("Evaluation options", { exact: true }).click();
  await expect(page.getByLabel("Tree search trials")).toHaveValue("3");
  await expect(page.getByLabel("Tree search seed")).toHaveValue("17");
  await page
    .getByRole("button", { name: "Inventory optimization", exact: true })
    .click();
  await page.getByLabel("On-hand inventory", { exact: true }).fill("50");
  await page.getByLabel("Lead time (periods)", { exact: true }).fill("2");
  await page
    .getByRole("button", { name: "Calculate replenishment", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /2. Replenishment decision/ }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "EOQ requires annual demand, ordering cost and annual holding cost.",
      { exact: true },
    ),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("saved simulation restores all controls and what-if horizon recalculates demand", async ({
  page,
}) => {
  const data = await (await page.request.post("/api/datasets/demo")).json();
  const run = await (
    await page.request.post("/api/forecast/train", {
      data: {
        dataset_id: data.dataset_id,
        store_id: "STORE_01",
        product_id: "SKU_001",
        models: ["naive"],
        horizon: 14,
        folds: 2,
      },
    })
  ).json();
  const plan = await (
    await page.request.post("/api/inventory/optimize", {
      data: {
        forecast_run_id: run.run_id,
        on_hand_inventory: 20,
        lead_time: 2,
      },
    })
  ).json();
  const simulation = await page.request.post("/api/inventory/simulate", {
    data: {
      plan_id: plan.plan_id,
      mode: "monte_carlo",
      trials: 100,
      seed: 17,
      horizon: 10,
      shortage_mode: "backorders",
    },
  });
  expect(simulation.status()).toBe(201);
  await page.goto(
    `/?dataset=${data.dataset_id}&view=inventory&plan=${plan.plan_id}`,
  );
  await expect(
    page.getByLabel("Simulation horizon", { exact: true }),
  ).toHaveValue("10");
  await expect(page.getByLabel("Simulation mode")).toHaveValue("monte_carlo");
  await expect(page.getByLabel("Monte Carlo paths")).toHaveValue("100");
  await expect(page.getByLabel("Simulation seed")).toHaveValue("17");
  await expect(page.getByLabel("Unfilled demand")).toHaveValue("backorders");
  await page.getByLabel("Simulation horizon", { exact: true }).fill("7");
  const pending = page.waitForResponse((r) =>
    r.url().endsWith("/inventory/scenario"),
  );
  await page
    .getByRole("button", { name: "Compare inputs as what-if", exact: true })
    .click();
  const response = await pending;
  expect(response.status(), await response.text()).toBe(201);
  const scenario = await response.json();
  expect(scenario.scenario.recommendation.forecast_horizon).toBe(7);
  expect(scenario.scenario.recommendation.forecast_p50_total).toBeCloseTo(
    run.forecast
      .slice(0, 7)
      .reduce((sum: number, point: { p50: number }) => sum + point.p50, 0),
  );
  await expect(
    page.getByRole("heading", { name: "What-if comparison", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});
