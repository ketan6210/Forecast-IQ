# Phase 3 implementation and verification

For the latest receipt-timing repairs, catalog integration and test results, see the
[October 13 continuation](phase3-continuation-2026-10-13.md). The results below are historical.

Baseline audit on 2026-09-28; final verification on 2026-09-30. This report describes the
implemented scope and measured evidence, without treating configured service targets as outcomes.

## Audit and repairs

Before architectural changes, all **137 backend tests** and **10 browser workflows** passed.
Phase 1 ingestion/validation/EDA, causal features, baseline models, chronological evaluation,
metrics, dashboard and Docker were working. Phase 2 statistical/tree/neural models, rolling
evaluation, tuning, champion selection, quantile calibration/metrics, native SHAP, independent
series and saved artifacts were working. No disconnected functional placeholders were found.
See the [audit](phase3-audit.md), which records the inspected areas and baseline evidence.

The local Python interpreter link was broken because its temporary base installation had
disappeared. It was repaired with a workspace-local ignored Python installation. The app
previously lacked versioned migrations; additive Alembic migrations now adopt the existing
tables and add inventory tables. Existing forecasting APIs and artifacts were preserved.
The temporary external npm installation lacks CLI files; Docker has a working npm build,
and installed local TypeScript/Prettier/Playwright CLIs were run directly with Node.

## Implemented functionality

- Saved Phase 2 forecast inputs with no retraining during inventory/scenario operations.
- Explicit on-hand/on-order/backorder positions; frequency-aware lead-time demand and supply coverage.
- No-buffer, demand-only, demand+lead uncertainty and forecast-quantile safety stock; configurable service.
- ROP/deficit/reorder trigger; EOQ with missing-input reasons and direct/rate holding cost styles.
- Target coverage, MOQ, order multiples, optional position cap and practical order recommendation.
- Sampled stockout probability, transparent risk bands, scenario shortage and optional revenue-at-risk.
- Deterministic and seeded Monte Carlo simulation, explicit initial arrivals, variable future lead times,
  lost-sales/backorder modes, holding/ordering/shortage costs and distributions.
- Immediate fill, period service, completed-cycle service, stockout rate, lost units, average inventory,
  coverage, and turnover only with supplied COGS.
- Finite service-level candidate comparison and four policy types with an explicit cost/fill-rate objective.
- ABC, XYZ and combined matrix, configurable thresholds, missing-data/currency exclusions.
- Single-series and batch APIs; inventory CSV import, row errors, paginated/filterable/sortable queue,
  portfolio summaries and formula-injection-safe recommendation CSV export.
- Immutable persisted inputs/results, saved simulations/comparisons/scenarios, SKU/location retrieval.
- Inventory dashboard, forecast/inventory uncertainty chart, position/ROP/SS, arrival events,
  policy tables, what-if comparisons, saved-plan links and mobile layout.
- Calculation explanations, documented assumptions, reproducible experiment and measured reports.

## Final validation

| Check | Result |
|---|---|
| Original Phase 1/2 tests before changes | 137 passed; 0 failed; 0 skipped |
| Original browser workflows before changes | 10 passed; 0 failed; 0 skipped |
| Final local Python suite | 187 passed; 0 failed; 0 skipped; 7.72 s |
| Final Docker Python suite, CPU PyTorch installed | 187 passed; 0 failed; 0 skipped; 15.26 s |
| Final Chromium browser suite against PostgreSQL | 13 passed; 0 failed; 0 skipped; 20.7 s |
| Ruff, backend/scripts/tests | Passed |
| TypeScript + production Vite build | Passed in Docker; local TypeScript also passed |
| Formatting of Phase 3 frontend changes | Passed scoped Prettier check |
| Existing PostgreSQL migration | `0002_inventory`, verified via SQL |
| 1,000-row isolated API benchmark | 1,000 successful; 0 failed; 0.422220 s full HTTP |
| Fresh browser saved-example restoration | Passed; no page errors |

The 50 new backend tests cover independent formulas, seed reproducibility, path dependence,
all inventory calculations, invalid/missing inputs, zero demand/stock/lead time, one-period
cases, 30/60/90-period horizons, daily/weekly/monthly holding/coverage, explicit arrival timing,
backlog/stock/order conservation, a hand-calculated cost ledger, cycle boundaries, segmentation,
policy feasibility/objective, no-retraining scenarios, all new APIs, exports and populated
legacy migration/idempotency. The 3 new browser workflows cover the full decision path,
import/filter/persistence, missing costs, mobile layout and validation; the full path also
restores a saved URL after clearing localStorage.

There is one upstream Starlette TestClient deprecation warning concerning httpx in each
Python suite; tests pass. A repository-wide Prettier probe found existing formatting differences
in `frontend/src/pages/Dashboard.tsx` and `frontend/e2e/advanced.spec.ts`; these unrelated files
were left unchanged. The scoped check of changed frontend files passes.

Commands used (workspace-specific paths):

```sh
DYLD_LIBRARY_PATH="$PWD/.venv/lib/python3.12/site-packages/torch/lib" .venv/bin/python -m pytest -q
.venv/bin/ruff check backend scripts tests
docker run --rm -v "$PWD:/workspace:ro" -w /workspace forecastiq-backend \
  python -m pytest -q -p no:cacheprovider
docker compose up -d --build
cd frontend
E2E_EXTERNAL=1 E2E_BASE_URL=http://127.0.0.1:5180 \
PLAYWRIGHT_BROWSERS_PATH=/private/tmp/forecastiq-browsers \
/private/tmp/node-v22.23.2-darwin-arm64/bin/node node_modules/@playwright/test/cli.js test
```

## Actual end-to-end example

The [measured walkthrough](phase3-measured-results.md) links to the live saved plan and
contains all inputs, forecast metrics, formulas, results, policy costs and timings.
Its [machine-readable evidence](phase3-measured-results.json) contains complete forecast,
trajectory, distributions, policy results and scenario outputs. The demonstration assumptions
are explicit; historical demand comes from the bundled synthetic retail dataset.

ETS was selected by the existing Phase 2 evaluation. For 30 daily periods: P50 sum
921.671014, marginal P90 scenario sum 1161.037681 (not a joint P90). Seven-period base
lead demand 216.928928, sampled lead P90 236.162624, safety stock 24.924877, ROP 241.853806.
Position 200 triggers a 624-unit recommendation; EOQ 612.372436 rounds to the 12-unit multiple.
Risk is high; configured safety-stock service target 95%. The 1,000-path simulation gives
98.106687% immediate fill, expected operating cost $319.297481, and completed-cycle service
55.65%. These measure different aspects of service; no 95% achieved-cycle guarantee is claimed.

The evaluated minimum-cost feasible policy uses a 90% quantile target, expected cost
$318.878007 and immediate fill 98.099232%, above the 95% minimum-fill constraint. The
independent deterministic simulation costs $312.709101. A multi-input what-if costs
$128.002040 under its changed assumptions. These are model estimates, not real-world savings.

See [the hand-checked 3-period ledger](phase3-methodology.md#hand-checked-ledger), with
holding=9, ordering=4, shortage=3, total=16 and fill=23/24, independently asserted in tests.

## Remaining limitations

- Forecast error bootstrap and bounded-tail interpolation are explicit approximations, not
  calibrated multivariate demand forecasts. Rare/unseen extremes, lead-specific error shapes,
  cross-SKU dependence and demand/lead correlation are not learned. Independent errors are the
  default; block length is user-configured, not selected by a statistical test.
- Gamma supplier lead times are assumed from supplied moments, not fitted to purchase history.
  Any sampled lead exposure exceeding the saved horizon rejects. Forecast horizons remain at most
  90 periods and the original Phase 2 history requirements still apply.
- Simulation uses static ROP/target, discrete periodic review and a finite horizon. No dynamic
  multi-echelon optimization, shared supplier capacity/budgets, perishability, returns, substitutions,
  censoring correction, purchase-price discounts, transport cost or terminal-value model is included.
- Cost/service optimization searches a small declared candidate set, not all policies, and uses the
  same paths for selection/reporting. Small cost differences may be simulation noise. No independent
  out-of-sample policy test, business service guarantee or observed savings claim is made.
- Inventory plans are snapshots entered or imported by users; no ERP/order execution, live stock
  feed or automatic purchase-order submission is implemented. Currency conversion is absent.
- CSV import requires existing forecast run IDs. It does not infer company costs or train missing
  series. The batch benchmark reuses one real forecast across synthetic locations and is not a
  1,000-SKU forecasting benchmark. Batch requests support at most 1,000 rows, CSV at most 2 MB.
- No enterprise authentication, production CI/CD, Kubernetes, monitoring/drift alerts, scheduled
  retraining, online feature store or distributed training: Phase 4 remains intentionally deferred.

No requested core Phase 3 capability is left as a UI placeholder. The items above describe
the limits of the implemented models and explicitly deferred integrations/infrastructure.
