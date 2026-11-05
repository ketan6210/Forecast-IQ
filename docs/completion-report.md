# Completion report through Phase 3

Verified on **2026-10-05**. The partial items identified in the
[completion audit](completion-audit.md) are implemented and pass the checks below.
The resumed completion pass verified the existing application changes and added this
report and [measured results](completion-measured-results.json); no application source
changes were needed during this pass.

## Verification

| Check | Result |
|---|---|
| Local Python suite, including actual neural training | 214 passed, 0 failed, 0 skipped; 10.79 s |
| Current Python suite in the existing Docker backend image | 214 passed, 0 failed, 0 skipped; 12.08 s |
| Chromium workflows against the Docker/PostgreSQL app | 15 passed, 0 failed, 0 skipped; 21.3 s |
| Ruff on backend, tests and scripts | Passed |
| TypeScript build | Passed |
| Vite production build | Passed; 2,176 modules, 1.36 s |
| Prettier on completion frontend files | Passed |
| Running API and PostgreSQL | Healthy; `/health` returned phase 3 |
| Current champion artifact reload | Forecast exactly equals the saved result |
| Older Phase 3 champion artifact reload | Forecast exactly equals the saved result |
| Long-history N-BEATS training and champion reload | Passed; N-BEATS selected over three baselines |
| 1,000-row inventory batch | 1,000 successful, 0 failed; 0.415216 s full in-process HTTP |

The running frontend serves the same asset filenames as the successful local build:
`index-CZz72wl2.js`, `charts-CgkXpnUA.js`, and `index-DKeKvH-H.css`. The checked backend
training, demand-summary and inventory API files also match the local source by SHA-256.
Docker tests mounted the current project read-only and disabled pytest's cache.

Both Python suites emitted one upstream Starlette TestClient/httpx deprecation warning.
The first local attempt failed nine tree-model tests because macOS could not locate
OpenMP. The documented workspace `DYLD_LIBRARY_PATH` setting resolved all nine failures;
no model or test expectations were changed. The temporary Node installation has a
working Node binary but missing npm CLI files, so frontend checks used installed CLIs
directly. Docker already contained the completion application changes.

## Closure of the audit's partial items

Paths are relative to the project root. The original audit remains a historical baseline.

| Audit item | Verified behavior | Implementation and evidence |
|---|---|---|
| CSV/schema mapping | Price is optional; absent price leaves revenue and value unavailable. Explicit numeric predictors are validated, persisted and restored. | `backend/app/data/validator.py`, `backend/app/data/repository.py`; `tests/integration/test_completion_api.py` |
| Daily/weekly/monthly frequency | Short date filters retain the declared calendar. Automatic training respects an explicitly declared daily dataset. | `backend/app/api/analytics.py`, `backend/app/services/advanced_training.py`; frequency integration tests |
| EDA statistics | Overview shows median, volatility, CV, calendar trend, MAD outliers and seasonal evidence without replacing missing demand with zero. | `backend/app/data/summary.py`, `frontend/src/pages/Dashboard.tsx`; hand-calculated summary tests |
| Baseline features | Lags 1/2/3/7/14/28 and rolling standard deviations 7/14/28 are causal. | `backend/app/features/feature_engineering.py`; `tests/unit/test_completion.py` |
| Tree-model predictors | Selected predictors reach regression, LightGBM, XGBoost, saved artifacts and native SHAP. Future predictors use information at the forecast origin only. | `backend/app/features/covariates.py`, `backend/app/models/supervised.py`; holdout-mutation, serialization and browser checks |
| Controlled tuning | Seeded randomized search evaluates bounded, distinct tree configurations on the same chronological folds; disabling tuning uses one configuration. | `backend/app/models/registry.py`; seed/budget tests and `tests/unit/test_phase2.py` leakage test |
| Advanced dashboard | Search budget and seed are editable and restored; selected predictors and their assumptions are shown. | `frontend/src/pages/Advanced.tsx`; `frontend/e2e/completion.spec.ts` |
| Inventory portfolio | Simulations with different shortage modes do not produce combined cost or fill-rate totals. | `backend/app/services/inventory.py`; mixed-mode integration test |
| What-if horizon | Both recommendation and simulation use the requested forecast prefix. The saved plan remains unchanged. | `backend/app/api/inventory.py`; API and browser assertions |
| Saved inventory dashboard | Saved simulation horizon, mode, paths, seed and shortage mode restore into the controls; costs show holding, ordering and shortage components. | `frontend/src/pages/Inventory.tsx`; saved-simulation browser workflow |

The full suites also preserve ingestion, validation, the Phase 1 workflow, statistical
and neural models, chronology, calibration, SHAP reconstruction, artifact integrity,
inventory formulas, conservation, policy feasibility, migrations, CSV exports, mobile
layout and delayed-response handling. The test count rose from the audit baseline of
187 Python tests and 13 browser workflows to 214 and 15 respectively.

## Measured forecast and inventory example

The [complete numeric evidence](completion-measured-results.json) was generated by
`scripts/run_completion_validation.py` against the local Docker API. It contains
comparison folds/trials, artifacts, forecasts, inputs, recommendations, simulations,
policy comparison, what-if results, portfolio results and the neural example.
The recorded measurement timestamp is `2026-10-05T04:42:15.325300+00:00`.

[Open the saved inventory example](http://localhost:5180/?dataset=017185e4-8fb0-4899-824c-ba82c3cf012c&view=inventory&plan=d9078b78-4340-4e8e-9403-6b8e80f7f3cd).
It is stored in the existing local Docker volumes and requires that stack to be running.

The retail history is the bundled synthetic data: STORE_01 / SKU_001, 365 daily
observations, a 30-period forecast and three expanding selection folds. **ETS** won
the chronological comparison. Nine candidates completed; N-BEATS was correctly skipped
because this example lacks 512 observations in every training fold. Both tree models
completed their seeded randomized searches.

| Untouched test metric, calibrated ETS P50 | Measured value |
|---|---:|
| MAE | 4.854744 |
| RMSE | 6.297065 |
| WAPE | 14.448643% |
| sMAPE | 14.868679% |
| MASE | 0.687546 |
| P10 / P50 / P90 pinball loss | 1.176784 / 2.427372 / 1.028074 |
| P10–P90 coverage | 80.000000% |
| Mean interval width | 15.739046 units |

The historical Phase 2 README table uses a different 28-period run and earlier tuning
configuration; these results do not replace its recorded evidence. Accuracy on this
synthetic series does not establish performance on other datasets.

Inventory inputs are demonstration assumptions: 160 on hand, 40 arriving in period 3,
no backorders, lead time 7 periods, target service 95%, annual demand 12,000,
ordering cost USD 50, annual unit holding cost USD 3.20, unit shortage cost USD 8,
unit cost USD 12, selling price USD 20, MOQ 48, order multiple 12 and target coverage
14 periods. Quantile calculations use 10,000 samples; simulations use 1,000 paths
and seed 42.

| Inventory output | Measured value |
|---|---:|
| Sum of 30 marginal P50 forecasts | 921.671014 units |
| Inventory position | 200 units |
| Expected seven-period lead-time demand | 216.928928 units |
| Safety stock | 24.924877 units |
| Reorder point | 241.853806 units |
| EOQ | 612.372436 units |
| Practical order, respecting the 12-unit multiple | 624 units |
| Monte Carlo immediate fill rate | 98.106687% |
| Monte Carlo completed-cycle service | 55.650000% |
| Expected holding / ordering / shortage cost | USD 78.359563 / 100.000000 / 140.937918 |
| Expected total operating cost | USD 319.297481 |
| Deterministic operating cost | USD 312.709101 |
| Changed-input what-if expected cost | USD 128.002040 |

The what-if changes lead time to 3 periods, service target to 99%, on-hand stock to
220 and ordering cost to USD 30. Its cost difference reflects these changed assumptions.
Fill rate, completed-cycle service and the configured target measure different things.
Summed marginal quantiles are scenarios, not calibrated quantiles of total demand.

The batch benchmark reuses one fitted forecast across 1,000 synthetic inventory
locations in temporary SQLite storage. It does not train 1,000 forecasting models.
The separate three-series example uses independently trained forecasts and verifies
portfolio/segmentation results and three exported CSV rows.

The prior Phase 3 saved run `78c059cd-44d7-4571-a4b9-1e5dc4205b18` reloaded successfully;
its predictions exactly matched its saved forecast. The new ETS champion also reloaded
with exact equality.

## Long-history neural execution check

The second example uses 700 synthetic daily Poisson counts with trend and weekly
seasonality, data seed 84, a 14-period horizon, three folds and 12 N-BEATS epochs.
It compares N-BEATS with naive, seasonal-naive and moving-average baselines; other model
families are not included in this separate check. All four candidates completed and
N-BEATS won. Reloading its champion artifact reproduced the saved forecast exactly.

| Untouched test metric | Measured value |
|---|---:|
| WAPE | 12.811639% |
| sMAPE | 13.682690% |
| MASE | 0.917231 |
| P10–P90 coverage | 92.857143% |

This verifies neural execution and persistence. Its MASE exceeds 0.9 and coverage exceeds
the earlier 80–90% target range, so those targets are not met in this neural example.

## Reproduction in this workspace

Run from the project root with the existing Docker stack on ports 8010/5180:

```sh
DYLD_LIBRARY_PATH="$PWD/.venv/lib/python3.12/site-packages/torch/lib" \
  .venv/bin/python -m pytest -q --tb=short
.venv/bin/ruff check backend tests scripts
docker compose run --rm --no-deps --volume "$PWD:/workspace:ro" \
  --workdir /workspace backend python -m pytest -q -p no:cacheprovider --tb=short
DYLD_LIBRARY_PATH="$PWD/.venv/lib/python3.12/site-packages/torch/lib" \
  .venv/bin/python -m scripts.run_completion_validation \
  --base-url http://127.0.0.1:8010 \
  --legacy-run 78c059cd-44d7-4571-a4b9-1e5dc4205b18
```

The validation script creates new demo records and rewrites the measured JSON. The
optional `--legacy-run` argument refers to an existing artifact in this workspace;
omit it on a fresh database. The backend requires the optional PyTorch runtime for
the long-history example. Timings and floating-point results can vary by platform.

From `frontend/`, using the available Node binary:

```sh
/private/tmp/node-v22.23.2-darwin-arm64/bin/node node_modules/typescript/bin/tsc -b
/private/tmp/node-v22.23.2-darwin-arm64/bin/node node_modules/vite/bin/vite.js build
E2E_EXTERNAL=1 E2E_BASE_URL=http://127.0.0.1:5180 \
  PLAYWRIGHT_BROWSERS_PATH=/private/tmp/forecastiq-browsers \
  /private/tmp/node-v22.23.2-darwin-arm64/bin/node node_modules/@playwright/test/cli.js test
/private/tmp/node-v22.23.2-darwin-arm64/bin/node node_modules/prettier/bin/prettier.cjs \
  --check src/App.tsx src/pages/Dashboard.tsx src/pages/Advanced.tsx \
  src/pages/Inventory.tsx src/types.ts src/advancedTypes.ts src/inventoryTypes.ts \
  e2e/completion.spec.ts
```

## Remaining limits

Predictors use forecast-origin carry-forward assumptions; no future-covariate upload
is added. Calendars remain daily, anchored weekly, month-start and month-end.
Residual bootstrap and pooled forecast-lead quantiles do not guarantee future coverage.
Inventory simulations use declared demand/lead-time assumptions and a finite candidate
policy search; reported costs are estimates rather than observed business savings.
The [Phase 3 methodology](phase3-methodology.md) and
[existing limitations](phase3-verification.md#remaining-limitations) still apply.
ERP integration, purchase-order execution, enterprise authentication, deployment
automation, monitoring and scheduled retraining remain outside the Phase 3 scope.
