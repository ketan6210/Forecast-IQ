const { test, expect } = require('../../frontend/node_modules/@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

test('audit reproduction: two-column upload still displays All 5 present', async ({ page }) => {
  const rows = Array.from({ length: 140 }, (_, i) => {
    const day = new Date(Date.UTC(2025, 0, i + 1)).toISOString().slice(0, 10);
    return `${day},${20 + i % 7}`;
  });
  const response = await page.request.post('/api/datasets/upload', {
    multipart: {
      file: { name: 'two-columns.csv', mimeType: 'text/csv', buffer: Buffer.from('date,units_sold\n' + rows.join('\n')) },
      store_column: '__single__', product_column: '__single__',
    },
  });
  expect(response.status()).toBe(201);
  const dataset = await response.json();
  expect(dataset.missing_value_summary.price).toBe(140);
  await page.goto(`/?dataset=${dataset.dataset_id}`);
  await page.getByRole('button', { name: 'Data quality', exact: true }).click();
  await expect(page.getByText('All 5 present', { exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(__dirname, 'quality-label.png'), fullPage: true });
  fs.writeFileSync(path.join(__dirname, 'quality-label.json'), JSON.stringify({
    source_columns: ['date', 'units_sold'], upload_status: response.status(),
    missing_price_rows: dataset.missing_value_summary.price,
    rendered_required_column_claim: 'All 5 present',
    finding: 'Hard-coded required-field status disagrees with optional price and synthesized identifiers.',
  }, null, 2));
});
