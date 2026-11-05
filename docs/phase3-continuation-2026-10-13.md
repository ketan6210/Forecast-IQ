# Phase 3 continuation — receipt timing and catalog integration

This update addresses the supply-timing defect and disconnected catalog identified in the
[October 12 repository audit](repository-audit-2026-10-12.md). Phase 3 now evaluates receipt
timing when reporting risk, shortages and operational priority. Saved offline forecasts can
be registered in the application, and the dashboard loads catalogs beyond 100 runs.

## Changed behavior

Inventory position remains **on-hand + on-order − backorders**. Risk separately compares
cumulative demand with stock actually available in each period of sampled lead time.
Receipts arrive before that period's demand. An earlier deficit remains a stockout event
even when later receipts clear it. Unknown arrival dates produce an explicit conservative
assessment; those orders remain in position but do not cover demand in the risk calculation.

For the audit regression—10 units of demand each day, zero on-hand stock, 1,000 units
arriving in period 20 and a two-period lead time—the recommendation now reports **high
risk, 100% sampled stockout probability and 20 units needing earlier availability**.
Position stays 1,000 and additional purchase quantity stays zero. Moving that delivery to
period 1 removes the exposure; moving it to period 2 still leaves the first 10-unit deficit.
These exact cases are regression-tested.

`expedite_quantity` is the immediate shortfall at the selected service quantile. It prompts
review of transfers or earlier receipts and is separate from purchase quantities, MOQ and
order multiples. The simulator continues to use the entered schedule; it does not invent
an expedited delivery. Shortfall quantiles are described as immediate stock requirements,
not simulated lost sales. Dashboard alerts, queue ordering, CSV export and portfolio counts
expose the new action. Old saved plans remain immutable and are flagged for recalculation.

`scripts/import_forecast_catalog.py` registers trusted local checkpoints using the selected
application dataset. It validates full history, prepared-data fingerprints, dates, quantile
ordering, calibration records, artifact metadata and checksums. It preserves source
provenance and training dates. Repeat imports skip matching intact records; conflicting or
damaged batches reject and roll back newly created records/files. Registration does not
unpickle artifacts or retrain models. Prediction subsequently loads the registered artifacts.
The [README](../README.md#register-saved-catalog-forecasts) gives local and Docker commands.

`GET /forecast/models` accepts `limit=1..500` and nonnegative `offset`, with deterministic
ordering for timestamp ties. Both forecasting and inventory selectors fetch subsequent
pages, deduplicate overlapping IDs and preserve abort behavior when a user changes datasets.

## Verification

| Check | Result |
|---|---|
| Full Python suite | 237 passed, 0 failed, 0 skipped |
| Chromium browser suite against PostgreSQL | 19 passed, 0 failed, 0 skipped |
| Ruff | Passed |
| TypeScript and Vite production build | Passed |
| Prettier, changed frontend files | Passed |
| Real saved catalog dry run | 500 validated; zero records/artifacts written |
| Real catalog registration | 500 imported in 24.43 seconds |
| Repeat registration | 500 skipped; no duplicate records |
| Catalog pagination | Five pages of 100 unique runs, then an empty page |
| Saved-model reloads | Five champion/calibrator pairs; all 450 forecast points matched exactly |
| Explainability | LightGBM explanations accessible for those five imported runs |
| Catalog inventory batch | 500 successful plans, 0 failed, 18.27 seconds |
| Portfolio | All 500 series represented with receipt-timing assessments |

The catalog batch used explicit **test assumptions**: zero on-hand, 10,000 on-order arriving
in period 20 and a seven-period lead time. All 500 plans flagged exposure while retaining
zero additional purchase quantities. These are not observed business inventory levels or
measured operating outcomes. No 500-series retraining or simulation was performed. Costs
and segmentation inputs were omitted, so their unavailable results remain explicit.

Evidence: [catalog results](phase3-catalog-evidence-2026-10-13.json),
[Python JUnit results](phase3-continuation-2026-10-13-checks/pytest.xml),
[browser results](phase3-continuation-2026-10-13-checks/playwright.json).
The Python suite emits the existing Starlette/httpx deprecation warning. Two initial new
browser assertions used incorrect accessible names/an option count; the corrected full
suite passes. The pagination browser test uses controlled list responses; the separate
PostgreSQL check verifies the actual 500 persisted runs through the real API.

Verification used an isolated PostgreSQL stack and existing dependency images with current
source mounted read-only, plus freshly built frontend assets. A fresh backend image build
was not performed. The documented CLI was also exercised against that stack. The original
running application database and the source catalog were not modified. Rebuild the app's
containers to run this source, then register the catalog against its uploaded dataset.

## Remaining scope

Multi-SKU recommendations still optimize each series independently. Joint purchasing-budget
or shared warehouse-capacity allocation is not implemented, so the broader Phase 3 status
remains **partial**. Forecast calibration quality and empirical-tail limitations are unchanged;
the configured service level is not a guarantee. Catalog import is an operator-only command
for trusted local artifacts, not an arbitrary model upload endpoint. A process crash can
leave an unregistered artifact directory, which must be inspected before retrying; the
importer refuses to overwrite existing directories. No Phase 4 work was introduced.
