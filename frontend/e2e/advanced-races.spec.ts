import { expect, test, type Page, type Request } from "@playwright/test";
import type { AdvancedRun } from "../src/advancedTypes";

async function savedDemoRun(page: Page): Promise<AdvancedRun> {
  await page.goto("/");
  const uploaded = page.waitForResponse((response) =>
    response.url().endsWith("/api/datasets/demo"),
  );
  await page.getByRole("button", { name: /Use Demo Dataset/ }).click();
  const dataset = await (await uploaded).json();
  await expect(
    page.getByRole("heading", { name: "Data quality report" }),
  ).toBeVisible();
  const trained = await page.request.post("/api/forecast/train", {
    data: {
      dataset_id: dataset.dataset_id,
      store_id: "STORE_01",
      product_id: "SKU_001",
      horizon: 7,
      folds: 2,
      models: ["naive"],
    },
  });
  expect(trained.status()).toBe(201);
  const run = (await trained.json()) as AdvancedRun;
  await page.evaluate(
    ({ dataset_id, run_id }) =>
      localStorage.setItem(`forecastiq.advanced.${dataset_id}`, run_id),
    run,
  );
  return run;
}

async function holdResponse(page: Page, endpoint: string) {
  let ready!: () => void;
  let release!: () => void;
  let handled!: () => void;
  const fetched = new Promise<void>((resolve) => {
    ready = resolve;
  });
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const fulfilled = new Promise<void>((resolve) => {
    handled = resolve;
  });
  const settled = new Promise<void>((resolve) => {
    const listener = (request: Request) => {
      if (!request.url().endsWith(endpoint)) return;
      page.off("requestfinished", listener);
      page.off("requestfailed", listener);
      resolve();
    };
    page.on("requestfinished", listener);
    page.on("requestfailed", listener);
  });
  await page.route(`**${endpoint}`, async (route) => {
    const response = await route.fetch();
    ready();
    await gate;
    await route.fulfill({ response }).catch(() => {
      // Correct cancellation can abort the browser request before delivery.
    });
    handled();
  });
  return {
    fetched,
    async finish() {
      release();
      await fulfilled;
      await settled;
      // Let browser delivery and React commit finish before checking persistent state.
      await page.evaluate(
        () =>
          new Promise<void>((resolve) => {
            requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
          }),
      );
    },
  };
}

test("delayed saved run cannot overwrite a newer series selection", async ({
  page,
}) => {
  const run = await savedDemoRun(page);
  const delayed = await holdResponse(page, `/api/forecast/runs/${run.run_id}`);
  await page
    .getByRole("button", { name: "Advanced forecasting", exact: true })
    .click();
  await delayed.fetched;
  await page.getByLabel("Advanced store").selectOption("STORE_02");
  await delayed.finish();
  await expect(page.getByLabel("Advanced store")).toHaveValue("STORE_02");
  await expect(page.locator(".champion-name")).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("editing controls while saved runs load keeps saved-run choices available", async ({
  page,
}) => {
  const run = await savedDemoRun(page);
  const delayed = await holdResponse(
    page,
    `/api/forecast/models?dataset_id=${run.dataset_id}`,
  );
  await page
    .getByRole("button", { name: "Advanced forecasting", exact: true })
    .click();
  await delayed.fetched;
  await page.getByLabel("Advanced store").selectOption("STORE_02");
  await delayed.finish();
  await expect(page.getByLabel("Advanced store")).toHaveValue("STORE_02");
  await expect(page.locator(".champion-name")).toHaveCount(0);
  await expect(
    page
      .getByLabel("Saved training run")
      .locator(`option[value="${run.run_id}"]`),
  ).toHaveCount(1);
});

test("delayed comparison cannot populate a newly selected series pair", async ({
  page,
}) => {
  await savedDemoRun(page);
  await page
    .getByRole("button", { name: "Advanced forecasting", exact: true })
    .click();
  await expect(page.locator(".champion-name")).toBeVisible();
  const delayed = await holdResponse(page, "/api/forecast/series-comparison");
  const select = page.getByLabel("Series to compare");
  const firstPair = JSON.stringify(["STORE_02", "SKU_001"]);
  const nextPair = JSON.stringify(["STORE_02", "SKU_002"]);
  await select.selectOption(firstPair);
  await page
    .getByRole("button", { name: "Compare series", exact: true })
    .click();
  await delayed.fetched;
  await select.selectOption(nextPair);
  await delayed.finish();
  const panel = page.locator(".panel").filter({
    has: page.getByRole("heading", { name: "Compare independent series" }),
  });
  await expect(panel.locator("tbody tr")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Compare series", exact: true })
    .click();
  await expect(panel.locator("tbody tr")).toHaveCount(2);
  await expect(panel.locator("tbody")).toContainText("STORE_02 / SKU_002");
  await expect(panel.locator("tbody")).not.toContainText("STORE_02 / SKU_001");
  await expect(page.getByRole("alert")).toHaveCount(0);
});
