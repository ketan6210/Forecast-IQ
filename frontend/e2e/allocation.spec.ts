import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";

for (const single of [false, true]) {
  test(`quality checks handle optional price with ${single ? "generated" : "supplied"} identifiers`, async ({
    page,
  }) => {
    const header = single
      ? "date,units_sold"
      : "date,units_sold,store_id,product_id";
    const rows = Array.from(
      { length: 140 },
      (_, i) =>
        `${new Date(Date.UTC(2025, 0, i + 1)).toISOString().slice(0, 10)},${20 + (i % 7)}${single ? "" : ",S1,P1"}`,
    );
    const response = await page.request.post("/api/datasets/upload", {
      multipart: {
        file: {
          name: "optional-price.csv",
          mimeType: "text/csv",
          buffer: Buffer.from([header, ...rows].join("\n")),
        },
        store_column: single ? "__single__" : "store_id",
        product_column: single ? "__single__" : "product_id",
      },
    });
    expect(response.status()).toBe(201);
    const dataset = await response.json();
    expect(dataset.missing_value_summary.price).toBe(140);
    await page.goto(`/?dataset=${dataset.dataset_id}`);
    await page
      .getByRole("button", { name: "Data quality", exact: true })
      .click();
    await expect(
      page.getByText("Required fields after mapping", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Validated", { exact: true })).toBeVisible();
    await expect(page.getByText("All 5 present", { exact: true })).toHaveCount(
      0,
    );
    await expect(page.getByText(/Price is optional/)).toBeVisible();
  });
}

test("joint budget/capacity allocation persists, exports and restores on mobile", async ({
  page,
}) => {
  const dataset = await (await page.request.post("/api/datasets/demo")).json();
  const plans = [];
  for (const sku of ["SKU_001", "SKU_002"]) {
    const training = await page.request.post("/api/forecast/train", {
      data: {
        dataset_id: dataset.dataset_id,
        store_id: "STORE_01",
        product_id: sku,
        horizon: 7,
        folds: 2,
        models: ["naive"],
        tune: false,
      },
    });
    expect(training.status()).toBe(201);
    const run = await training.json();
    const response = await page.request.post("/api/inventory/optimize", {
      data: {
        forecast_run_id: run.run_id,
        on_hand_inventory: 0,
        lead_time: 2,
        unit_cost: 3,
        currency: "USD",
        minimum_order_quantity: 6,
        order_multiple: 3,
      },
    });
    expect(response.status()).toBe(201);
    plans.push(await response.json());
  }
  await page.goto(`/?dataset=${dataset.dataset_id}&view=inventory`);
  await page.getByLabel("Allocate SKU_001 / STORE_01").check();
  await page.getByLabel("Allocate SKU_002 / STORE_01").check();
  await page.getByLabel("Purchasing budget", { exact: true }).fill("36");
  await page
    .getByLabel("Available capacity for new orders", { exact: true })
    .fill("18");
  await page.getByLabel("Capacity unit", { exact: true }).fill("m3");
  await page.getByLabel("Space SKU_001 / STORE_01").fill("2");
  await page.getByLabel("Space SKU_002 / STORE_01").fill("2");
  await page.getByLabel("Priority SKU_002 / STORE_01").fill("2");
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/inventory/allocate") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Allocate selected plans", exact: true })
    .click();
  const allocationResponse = await response;
  expect(allocationResponse.status()).toBe(201);
  const allocation = await allocationResponse.json();
  expect(
    allocation.items.map(
      (i: { allocated_quantity: number }) => i.allocated_quantity,
    ),
  ).toEqual([0, 9]);
  expect(allocation.purchase_cost).toBe(27);
  expect(allocation.capacity_used).toBe(18);
  const result = page.getByRole("region", { name: "Allocation result" });
  await expect(result).toContainText("Optimal under the stated objective");
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export allocation CSV" }).click();
  expect((await download).suggestedFilename()).toContain(
    allocation.allocation_id,
  );
  await page.reload();
  await page
    .getByLabel("Saved allocation", { exact: true })
    .selectOption(allocation.allocation_id);
  await expect(result).toContainText("27 USD");
  const evidence = process.env.ALLOCATION_EVIDENCE_DIR;
  if (evidence) {
    await mkdir(evidence, { recursive: true });
    await writeFile(
      `${evidence}/allocation-example.json`,
      JSON.stringify(allocation, null, 2) + "\n",
    );
    await result.screenshot({
      path: `${evidence}/allocation-desktop.png`,
      animations: "disabled",
    });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(result).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  const table = result.locator(".table-wrap");
  expect(
    await table.evaluate((element) => {
      element.scrollLeft = element.scrollWidth;
      return element.scrollLeft;
    }),
  ).toBeGreaterThan(0);
  await table.evaluate((element) => (element.scrollLeft = 0));
  if (evidence)
    await result.screenshot({
      path: `${evidence}/allocation-mobile.png`,
      animations: "disabled",
    });
  for (const p of plans) {
    const unchanged = await (
      await page.request.get(`/api/inventory/plans/${p.plan_id}`)
    ).json();
    expect(unchanged.recommended_order_quantity).toBe(
      p.recommended_order_quantity,
    );
  }
});
