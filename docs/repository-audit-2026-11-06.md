# ForecastIQ repository audit

Core verification: November 6, 2026. Supplemental UI reproduction: November 7, 2026.
Audited revision: `07f2aa7` on `main`. Application source was unchanged throughout this audit.

## 1. OVERALL STATUS

| Phase | Status | Decision |
|---|---|---|
| Phase 1 | **PARTIAL** | All core foundation functions work. One inaccurate, hard-coded validation result remains in the quality dashboard. |
| Phase 2 | **COMPLETE** | Requested forecasting capabilities are implemented, connected, tested and exercised. |
| Phase 3 | **PARTIAL** | Substantial working inventory implementation; multi-SKU planning does not jointly allocate shared budgets or warehouse capacity. |
| Phase 3 Readiness | **READY** | No blocking Phase 1/2 forecasting dependency was found. Continue the existing Phase 3 implementation. |

**IS PHASE 1 COMPLETE? NO**, under the requested strict standard including truthful frontend checks. Its computational foundation is complete; the remaining defect is small and does not block forecasting or inventory work.

**IS PHASE 2 COMPLETE? YES**, within the supported frequencies, history requirements and model assumptions described below.

**IS PHASE 3 ALREADY IMPLEMENTED? PARTIALLY IMPLEMENTED.**

Status meanings: COMPLETE means source, integration and relevant execution support the requested behavior; PARTIAL means a named portion remains incomplete; MISSING means no implementation; BROKEN means a reproduced incorrect behavior; UNTESTED means runtime verification was unavailable. Completion does not mean universal forecasting accuracy, guaranteed service levels, or production certification.

The previous documentation-based Phase 1 conclusion is narrowed here because the fresh audit reproduced a quality-screen defect. The older receipt-timing and disconnected-catalog findings are **resolved in current source**, independently reverified below.

Scope covered: all backend package areas, frontend pages and API wrapper, database schema/migrations, data and feature processing, model families, evaluation/calibration/explainability, inventory/simulation, existing tests, Docker/configuration, scripts, both notebooks, bundled demo, local imported dataset, saved catalog and artifact manifests. Existing reports were treated as historical claims, not new test evidence.

## 2. PHASE 1 AUDIT

The relevant existing tests include `test_validation.py`, `test_features.py`, `test_models.py`, `test_evaluation.py`, `test_completion.py`, `test_api.py`, `test_completion_api.py`, and browser workflows. All passed in this audit.

| Feature | Status | Evidence | Problem |
|---|---|---|---|
| CSV upload/input | COMPLETE | [loader](../backend/app/data/loader.py), [upload API](../backend/app/api/datasets.py); browser uploads and fresh 913,000-row upload | UTF-8, 25 MB and one-million-row defaults apply. |
| Date column selection | COMPLETE | [repository mapping](../backend/app/data/repository.py), [upload UI](../frontend/src/App.tsx); mapped monthly browser test | None found. |
| Demand/target selection | COMPLETE | Same mapping pipeline; mapped-target API/browser tests | None found. |
| Optional SKU/store identifiers | COMPLETE | `__single__`, `sku_id`, custom mappings and Kaggle aliases in repository; fresh two-column upload | Missing IDs require explicit single-series mapping unless recognized aliases exist. |
| Missing values | COMPLETE | [validator](../backend/app/data/validator.py), [preparation](../backend/app/data/frequency.py); missing-target tests | Missing demand blocks training unless zero filling is explicitly chosen; optional price is not invented. |
| Duplicates | COMPLETE | Validator normalizes and removes exact duplicates; conflicting series/date values reject | No silent aggregation of conflicting observations. |
| Invalid dates | COMPLETE | Validator rejects invalid and intraday timestamps; frequency alignment checks | Calendar-period inputs only. |
| Invalid target values | COMPLETE | Numeric, finite, nonnegative and all-missing validation; parameterized tests | None found. |
| Missing periods | COMPLETE | Calendar reindexing and observation flags; API zero-policy tests | Automatic zero filling intentionally absent. |
| Insufficient history | COMPLETE | Upload warnings, baseline 90-period guard, configuration-specific advanced guard | Advanced training requirements grow with horizon and folds. |
| Daily/weekly/monthly frequency | COMPLETE | [frequency handling](../backend/app/data/frequency.py), weekly/MS/ME API tests and monthly UI execution | Legacy `/forecast` is daily-only; `/forecast/train` handles all supported frequencies and includes baselines. |
| Chronological ordering | COMPLETE | Validator sorting, per-series preparation, split tests | None found. |
| EDA demand trends | COMPLETE | [summary](../backend/app/data/summary.py), [analytics API](../backend/app/api/analytics.py), dashboard | Descriptive slope, not a causal claim. |
| EDA distributions | COMPLETE | Observed mean, median, standard deviation, CV, min/max; hand-checked statistics tests | Descriptive distribution summaries; no dedicated histogram/density chart. |
| EDA seasonality | COMPLETE | [diagnostics](../backend/app/data/diagnostics.py), weekday/month charts, ACF/PACF | Heuristic detection; gaps suppress unsupported ACF claims. |
| EDA outliers | COMPLETE | Scaled MAD observations and counts; dashboard details and tests | Zero MAD yields no flags; outliers are not automatically removed. |
| EDA missing-data information | COMPLETE | Validation reports, gap-aware analytics and missing-value table | Aggregate totals may be partial when some constituent observations are missing; disclosed in notes. |
| Basic visualizations | COMPLETE | [dashboard](../frontend/src/pages/Dashboard.tsx), [charts](../frontend/src/components.tsx); desktop/mobile browser workflows | None found. |
| Lag features | COMPLETE | [feature engineer](../backend/app/features/feature_engineering.py): 1, 2, 3, 7, 14, 28; unit tests | Period-based lags; per-series grouping. |
| Rolling means | COMPLETE | Shifted 7/14/28-period windows; hand-checked tests | None found. |
| Rolling standard deviations | COMPLETE | Shifted 7/14/28-period sample standard deviations; tests | None found. |
| Calendar features | COMPLETE | Weekday, day, week, month, quarter, year and weekend; tests | None found. |
| Leakage-safe transformations | COMPLETE | Target features shift before rolling; covariates forward-fill only | Future external values are assumed at forecast origin rather than read from holdout data. |
| No future target data | COMPLETE | Prefix-only training and recursive predictions; target-mutation tests | No major leakage found in inspected paths. |
| Train-only scalers/encoders | COMPLETE | [linear model](../backend/app/forecasting/linear_regression.py), [supervised models](../backend/app/models/supervised.py); fresh imputer/scaler per fit | IDs are excluded rather than encoded; no global target encoder found. |
| Chronological splits | COMPLETE | [splitter](../backend/app/evaluation/splitter.py), fixed-origin validation and test | 70/15/15 for legacy baselines; advanced folds separately verified. |
| Naive baseline | COMPLETE | [implementation](../backend/app/forecasting/naive.py), model/API tests | Last observed demand repeated, not a fabricated forecast. |
| Seasonal Naive baseline | COMPLETE | [implementation](../backend/app/forecasting/seasonal_naive.py), [period baselines](../backend/app/models/baselines.py); tests | Season depends on workflow/frequency. |
| Moving Average baseline | COMPLETE | [implementation](../backend/app/forecasting/moving_average.py), model tests | None found. |
| Linear Regression baseline | COMPLETE | Causal features, train-only sklearn pipeline and recursive forecast; tests and live training | Negative predictions clipped at zero, explicitly disclosed. |
| MAE | COMPLETE | [metrics](../backend/app/evaluation/metrics.py); hand calculation and independent audit recomputation | None found. |
| RMSE | COMPLETE | Same, including independent audit recomputation | None found. |
| WAPE | COMPLETE | Same; zero-demand and independent recomputation tests | Undefined denominator returns null, not an invented percentage. |
| sMAPE | COMPLETE | Same; zero-pair convention and independent recomputation | Ratios are fractions in API and percentages in UI. |
| MASE | COMPLETE | Training-only seasonal scale; hand calculation and short/constant-history tests | Undefined scale returns null. |
| Model comparison | COMPLETE | [trainer](../backend/app/forecasting/trainer.py), [comparison UI](../frontend/src/pages/Comparison.tsx); browser comparison | Selection uses validation, not final test. |
| FastAPI/backend | COMPLETE | [app/router registration](../backend/app/main.py); integration tests and Docker HTTP workflows | None found in requested scope. |
| Basic dashboard and quality display | PARTIAL | Real API-backed pages pass browser tests; [Quality.tsx](../frontend/src/pages/Quality.tsx) line 119 | Required-columns check always displays `All 5 present`; backend requires four normalized fields, with price optional and IDs synthesizable. |
| Database/persistence | COMPLETE | SQLAlchemy models and Alembic revisions; old-schema migration test and fresh PostgreSQL startup | App DB and artifact storage must be retained together. |
| Docker | COMPLETE | Fresh backend/frontend image builds, healthy PostgreSQL/backend, 19 browser workflows | Core Docker image intentionally omits optional PyTorch. |
| Logging/error handling | COMPLETE | [main exception handlers](../backend/app/main.py), domain errors, structured timings; invalid-input/failure tests and Docker logs | One dependency deprecation warning remains. |
| Automated testing | COMPLETE | 237 existing Python tests and 19 existing browser tests passed | Existing tests did not detect the required-columns label defect. |
| README/run instructions | COMPLETE | Current README/config matched successful build and workflows; local OpenMP workaround worked | Older reports remain historical; prior test counts are not current results. |

**Missing Phase 1 items:**

1. Replace the hard-coded required-columns success text with a truthful result based on the accepted schema/mapping. Add a focused regression for price-free and single-series uploads. Reproduction: upload 140 rows containing only `date,units_sold`, map both identifiers to `__single__`; upload succeeds, all 140 price values are missing, yet the screen says `All 5 present`. See [captured UI](repository-audit-2026-11-06-checks/quality-label.png) and [probe result](repository-audit-2026-11-06-checks/quality-label.json).

No missing computational foundation was found. This UI defect is not a Phase 3 blocker.

## 3. PHASE 2 AUDIT

Source was traced through [training orchestration](../backend/app/services/advanced_training.py), [API routes](../backend/app/api/advanced.py), saved artifacts, and [the advanced dashboard](../frontend/src/pages/Advanced.tsx). Runtime evidence includes the existing Phase 2 tests, browser suite and [fresh forecast pipeline](repository-audit-2026-11-06-checks/forecast-pipeline.json).

| Feature | Status | Evidence | Problem |
|---|---|---|---|
| ARIMA | COMPLETE | [statistical models](../backend/app/models/statistical.py); fresh successful candidate | Bounded low-order model; convergence failures are reported. |
| SARIMA where appropriate | COMPLETE | Same; training-prefix seasonality checks; fresh successful candidate | Adapts to nonseasonal ARIMA when seasonal evidence is insufficient. |
| ETS/Holt-Winters | COMPLETE | Same; actual fitted ETS won the fresh demo | Additive trend/seasonal behavior chosen from training data. |
| LightGBM | COMPLETE | [model](../backend/app/models/lightgbm_model.py), recursive features; fresh successful tuned model | Requires native OpenMP runtime. |
| XGBoost | COMPLETE | [model](../backend/app/models/xgboost_model.py); fresh successful tuned model and contribution tests | Requires compatible native runtime. |
| N-BEATS or fallback | COMPLETE | [three residual blocks](../backend/app/models/deep_forecaster.py); neural unit test and [700-period API run](repository-audit-2026-11-06-checks/neural-pipeline.json) | At least 512 periods in every training fold and optional PyTorch; short demo correctly reports skipped candidate. |
| Multiple rolling/walk-forward folds | COMPLETE | [backtest plan](../backend/app/evaluation/backtesting.py); 2–5 disjoint folds, expanding/rolling windows | Final calibration and test are reserved first. |
| Configurable horizon | COMPLETE | [request schema](../backend/app/schemas/advanced.py), APIs and UI | 1–90 periods. Longer prediction requires retraining/calibration. |
| Chronological evaluation; no random CV | COMPLETE | Prefix slicing and timestamp boundaries; mutation tests | Parameter sampling is random; time partitions are not shuffled. |
| Backtest MAE | COMPLETE | Per-fold actuals/predictions and metric calculations | None found. |
| Backtest RMSE | COMPLETE | Same | None found. |
| Backtest WAPE | COMPLETE | Same, plus eligibility requires defined WAPE across folds | All-zero demand uses explicit naive fallback. |
| Backtest sMAPE | COMPLETE | Same | None found. |
| Backtest MASE | COMPLETE | Same, frequency-specific training scale | Null for undefined scaling denominator. |
| Mean/median/std aggregates | COMPLETE | `metric_summary`; tested summaries and dashboard | Standard deviation is sample std across multiple folds. |
| Model comparison | COMPLETE | Persisted candidate/trial/fold outcomes; `/forecast/model-comparison` | Failed candidates retain reasons. |
| Champion selection | COMPLETE | [ranking](../backend/app/evaluation/model_selection.py); validation WAPE, variability and tie-breaks | Champion is selected before calibration/test evaluation. |
| Time-series-aware tuning | COMPLETE | [parameter sampling](../backend/app/models/registry.py); every candidate uses same chronological folds | Bounded tree search; no claim of exhaustive tuning of every family. |
| P10 | COMPLETE | [held-out residual calibrator](../backend/app/evaluation/probabilistic_metrics.py); fresh pipeline | Empirical marginal quantile, pooled across leads. |
| P50 | COMPLETE | Same; median residual adjustment | May differ from uncalibrated raw model prediction. |
| P90 | COMPLETE | Same; finite-rank tail correction | Temporal dependence/refits limit coverage guarantees. |
| P10 ≤ P50 ≤ P90 | COMPLETE | Ordered residual offsets, common nonnegative clipping, tests and all 500 catalog validations | No crossing quantiles found. |
| Pinball loss | COMPLETE | Actual residual loss; hand tests and independent pipeline recomputation for all three levels | None found. |
| Interval coverage | COMPLETE | Actual test observations inside P10/P90; recomputed independently | Demo's measured 80% is one sample, not a fixed output or guarantee. |
| Interval width | COMPLETE | Mean P90−P10; tests and API output | None found. |
| SHAP/equivalent | COMPLETE | [native TreeSHAP](../backend/app/explainability/shap_values.py); contribution sums checked against raw predictions | Candidate explanations only; pre-clipping/pre-calibration, not causal effects. |
| Feature importance | COMPLETE | Mean absolute contributions, signed contributions and local drivers; UI/browser verification | Summarizes up to 200 recent training rows. |
| Multi-series SKU/store/location support | COMPLETE | Independent models keyed by store/product; series comparison; 500 actual catalog series | No global model, hierarchy reconciliation or cold-start model. Those are outside the listed requirements. |
| Model artifact persistence | COMPLETE | [checksummed joblib/metadata](../backend/app/services/artifacts.py); reload tests and five existing catalog champion/calibrator pairs | All 3,500 catalog binaries checked; prediction reload sampled five LightGBM champions, not all 500 models. |
| Forecast APIs | COMPLETE | Train, predict, saved run, list, backtest, comparison, SHAP, export and series-comparison routes; runtime tests | Training is synchronous and serialized per process. |
| Forecast dashboard | COMPLETE | Real API-backed configuration, metrics, bands, diagnostics, SHAP and restoration | Desktop/mobile and stale-response tests passed. |
| Tests | COMPLETE | Phase 2 unit/integration tests, leakage mutations, eligible neural execution and browser workflows | None failing. |

**Missing Phase 2 items:** None from the requested implementation checklist.

Limitations do remain: fixed future covariate assumptions, finite search budgets, independent series, model/calibration accuracy on representative business data, pooled lead residuals, and finite empirical tails. These are disclosed model/scope limits, not missing P10/P50/P90 or fake backtesting.

## 4. PHASE 3 AUDIT

**IS PHASE 3 ALREADY IMPLEMENTED? PARTIALLY IMPLEMENTED.**

The implementation flows from a saved `AdvancedRun` into `InventoryPlan`, then persisted simulations/comparisons. Inventory services do not retrain forecasting models. Existing unit/API tests, six inventory browser workflows plus completion workflows, [the fresh inventory pipeline](repository-audit-2026-11-06-checks/inventory-pipeline.json), and [500-series catalog exercise](repository-audit-2026-11-06-checks/catalog.json) verify this connection.

| Feature | Status | Evidence | Problem |
|---|---|---|---|
| Forecast → inventory integration | COMPLETE | [saved forecast loader](../backend/app/services/inventory.py); API integration forbids training during inventory operations; real catalog batch | Requires a saved advanced forecast. |
| Inventory position | COMPLETE | [formulas](../backend/app/inventory/formulas.py): on-hand + on-order − backorders; hand and API tests | Physical availability is evaluated separately from position. |
| Lead-time demand | COMPLETE | [recommendation](../backend/app/inventory/recommendations.py): period P50 sum plus sampled aggregate distribution | P50 sum is a median-based proxy, not a proven mathematical expectation. |
| Demand-uncertainty safety stock | COMPLETE | Analytical `z × sigma × sqrt(L)` path; formula tests | Assumes period independence; historical std may include trend/seasonality. |
| Lead-time uncertainty | COMPLETE | Analytical combined variance and rounded Gamma lead-time draws; reproducibility tests | Gamma moments are pre-rounding; uncovered sampled leads reject instead of truncating. |
| Forecast-quantile safety stock | COMPLETE | Sample aggregate demand then take selected quantile minus base demand | Does not sum marginal P90 values and call them joint P90. |
| Configurable 90/95/97.5/99% service levels | COMPLETE | [schema](../backend/app/schemas/inventory.py), UI and policy grid tests | These are configured targets, not guaranteed achieved service. |
| Reorder point | COMPLETE | Base lead-time demand + safety stock; formula/API checks | Static policy over the saved horizon. |
| EOQ | COMPLETE | Square root of `2 × annual demand × ordering cost / annual holding cost`; hand check | Missing costs/demand or zero holding cost return unavailable reason. |
| Recommended order quantity | COMPLETE | Trigger on position; target gap/EOQ/MOQ/multiple; rounding and per-series cap tests | Heuristic per-series policy; no shared resource allocation. |
| MOQ | COMPLETE | Order calculation and simulation enforce minimum feasible quantity | Infeasible caps yield zero and a reason. |
| Order multiples | COMPLETE | Round up, then round feasible cap down; tests | None found. |
| Days/periods of supply | COMPLETE | On-hand / mean forecast demand; frequency-aware units | Zero demand returns unavailable; average-rate coverage, not dated depletion prediction. |
| Stockout risk | COMPLETE | [supply exposure](../backend/app/inventory/supply.py); receipt schedules applied before demand; late-receipt regression passes | Unscheduled on-order stock excluded conservatively from risk. |
| Shortage/lost sales | COMPLETE | Immediate shortfall quantiles and [simulated lost sales/backorders](../backend/app/simulation/inventory_simulator.py) | Immediate stock needed and simulated lost units are distinct and labeled. |
| Holding cost | COMPLETE | End-period on-hand × annual holding / periods per year; hand ledger/frequency tests | Requires provided direct cost or unit cost and rate. |
| Ordering cost | COMPLETE | Cost charged once per placed order; ledger tests | Missing cost stays unavailable. |
| Stockout cost | COMPLETE | Cost per newly unfilled unit; ledger tests | Backorder penalty is not a recurring backlog-age charge. |
| Total inventory cost | COMPLETE | Holding + ordering + stockout; independent sum assertion | Excludes purchasing cost/profit; null unless all operating costs known. |
| Inventory simulation | COMPLETE | Receipt → backlog → demand → review → order ledger; hand tests, API/UI runs | Static periodic-review policy and finite horizon; no terminal cost assumption. |
| Monte Carlo simulation | COMPLETE | [seeded demand/lead draws](../backend/app/simulation/demand.py); distributions, reproducibility, fresh 1,000-path run | Residual bootstrap or explicit bounded-tail quantile interpolation; model uncertainty remains. |
| Service-level comparison | COMPLETE | Four configured levels evaluated with common random numbers | Above-P90 tails rely on bootstrap data or interpolation assumptions. |
| Inventory-policy comparison | COMPLETE | [finite cost/mean-fill constraint search](../backend/app/inventory/policies.py), persisted API/UI results | Feasible best among evaluated candidates, not a proof of global optimum. |
| ABC analysis | COMPLETE | [annual consumption value ranking](../backend/app/inventory/analytics.py); hand/API tests | Requires annual demand and unit cost; unknown values remain unclassified. |
| XYZ analysis | COMPLETE | Historical sample std/mean and configurable thresholds | Zero mean/insufficient history stays unclassified. |
| ABC–XYZ segmentation | COMPLETE | Combined classes, counts, API/UI | Descriptive segmentation, not an automatic prescription. |
| What-if analysis | COMPLETE | `/inventory/scenario` recalculates baseline and changed assumptions over selected horizon | Saved plan stays unchanged; both scenarios share forecast and simulation seed. |
| Multi-SKU inventory optimization | PARTIAL | `/inventory/batch` loops over independent `create_plan` calls; 500 genuine distinct series exercised | Joint budget and warehouse-capacity allocation are MISSING. A per-SKU position cap is not a shared constraint. |
| Portfolio inventory KPIs | COMPLETE | Latest plan per dataset/store/SKU/location; guarded sums and matching-scope simulation aggregation | Costs need complete common currency; service averages weight series equally. |
| Inventory APIs | COMPLETE | [routes](../backend/app/api/inventory.py): optimize/batch/import/list/detail/simulate/policies/scenario/KPIs/ABC/export | Catalog registration is trusted operator CLI, not arbitrary artifact upload. |
| Inventory dashboard | COMPLETE | [page](../frontend/src/pages/Inventory.tsx); real forms/results/simulation/what-if/segmentation; browser tests | No required core panel was found to be a static mock. |
| Replenishment table | COMPLETE | Filters, search, sort, pagination, CSV, restoration and expedite priority | Old plans without timing checks are flagged for recalculation. |
| Inventory tests | COMPLETE | Formulas, quantity conservation, costs, lead times, receipt timing, API persistence and browser workflows pass | Joint allocation has no implementation or tests. |
| Documentation | COMPLETE | [methodology](phase3-methodology.md), current README and API schemas match inspected behavior | Historical verification reports must not be read as current full-completion certification. |

The historical late-receipt defect is no longer reproduced: 10 units/day, zero stock, 1,000 units arriving in period 20 and lead time two reports high risk and a 20-unit immediate shortfall while keeping position at 1,000 and additional purchasing at zero. Tests also cover period-one and period-two receipts.

The catalog is connected: the audit validated and registered 500 existing forecasts, repeated registration without duplicates, paginated five batches of 100, reloaded five champion/calibrator pairs to reproduce 450 dated quantile triplets exactly, then created 500 successful plans. These checks used temporary SQLite; the complete browser suite separately exercised freshly built Docker/PostgreSQL. No 500-series retraining or simulation was performed. Inventory assumptions in the catalog probe are deliberately synthetic.

## 5. PHASE 3 READINESS

**READY FOR PHASE 3: YES. PHASE 3 READINESS: READY.**

| Prerequisite | Status | Fresh verification |
|---|---|---|
| Working champion model | COMPLETE | ETS selected/fitted/reloaded for the retail demo; LightGBM for the neural-eligible example. |
| Rolling backtesting | COMPLETE | Multiple chronological folds, reserved calibration/test and mutation tests. |
| WAPE/sMAPE/MASE | COMPLETE | Real calculations, zero-denominator handling and passing hand checks. |
| P10/P50/P90 | COMPLETE | Ordered empirical forecasts; probabilistic losses independently recomputed. |
| Correct frequency | COMPLETE | Daily, anchored weekly and MS/ME source and API tests; monthly UI run. |
| SKU/store identifiers | COMPLETE | Stable mappings and 500 independent catalog series. |
| Saved forecast outputs | COMPLETE | DB JSON, metadata/checksummed models, catalog registration and exact sampled reloads. |
| Stable forecast API | COMPLETE | Train/retrieve/predict/export/backtest/SHAP through integration tests and browser HTTP traffic. |
| Working tests | COMPLETE | All 256 existing tests passed. |
| No major leakage | COMPLETE | Causal features, training-only transforms, chronological tuning; target/covariate/calibration/test mutation tests pass. |

**Blocking Phase 3: none found in the requested Phase 1/2 dependencies.** The inaccurate quality label is nonblocking. Continue Phase 3 rather than rebuilding it. Readiness describes implementation dependencies; validating forecast coverage and inventory service on representative operational data remains separate work.

## 6. TEST RESULTS

Existing automated suites:

| Suite | Total | Passed | Failed | Skipped | Time |
|---|---:|---:|---:|---:|---:|
| Python: 175 unit + 62 integration | 237 | 237 | 0 | 0 | 10.37 s |
| Chromium against fresh Docker/PostgreSQL | 19 | 19 | 0 | 0 | 24.54 s |
| **Total existing tests** | **256** | **256** | **0** | **0** | — |

Evidence: [pytest log](repository-audit-2026-11-06-checks/pytest.log), [JUnit XML](repository-audit-2026-11-06-checks/pytest.xml), [browser log](repository-audit-2026-11-06-checks/playwright.log), [browser JSON](repository-audit-2026-11-06-checks/playwright.json).

Additional checks: Ruff passed; TypeScript project build and Vite production build passed; fresh Docker backend/frontend builds completed; PostgreSQL applied both Alembic revisions; [backend startup/API logs](repository-audit-2026-11-06-checks/docker-backend.log) confirm this. Both notebooks' 11 code cells executed as Python without modifying the notebooks ([results](repository-audit-2026-11-06-checks/notebooks.json)).

The separate audit-only browser probe passed **1/1**, deliberately confirming the current wrong quality label rather than checking a fix. It is excluded from the 256 existing-test count. Its source and screenshot are retained alongside the report.

No important test failures occurred. The Python run emitted one existing Starlette/httpx deprecation warning. Initial sandbox access to Docker and the browser download required escalation; these were environment-access issues and the subsequent executions succeeded. Browser tests include controlled delayed responses, pagination and old-plan payloads to test UI behavior; core forecast/inventory workflows call the real application. Catalog pagination was independently verified with actual persisted records.

Fresh end-to-end results on the bundled **synthetic** 365-period STORE_01/SKU_001 data, three folds, 30-period horizon:

| Measure | Observed result |
|---|---:|
| Champion | ETS |
| Test MAE | 4.903506 |
| Test RMSE | 6.355447 |
| Test WAPE | 14.593767% |
| Test sMAPE | 15.038112% |
| Test MASE | 0.694452 |
| P10/P50/P90 pinball loss | 1.180683 / 2.451753 / 1.028142 |
| Test P10–P90 coverage | 80.000000% |
| Mean interval width | 15.796675 units |
| Saved model/calibrator reload | Forecast reproduced exactly |
| Tree explanations | LightGBM and XGBoost |

All nine non-neural candidates completed this demo. N-BEATS reported insufficient per-fold history. A separate 700-period synthetic example actually trained N-BEATS through `/forecast/train` using three folds and two epochs, persisted it, and produced evaluated quantiles; the champion there was LightGBM. The neural serialization unit test also ran, with no skipped tests.

Under the explicitly supplied inventory demo inputs, position was **200**, base lead-time demand **216.237193**, safety stock **25.261755**, reorder point **241.498947**, EOQ **612.372436** and order quantity **624**, a multiple of 12. The 1,000-path simulation returned **98.130683% immediate fill**, **55.7% completed-cycle service**, and **317.308917 USD expected operating cost**. These are simulated outcomes under demonstration assumptions, not measured savings or a guaranteed 95% cycle-service result.

Reproduction commands and probes are preserved in [the verification directory](repository-audit-2026-11-06-checks/README.md). The local Python run used the documented macOS OpenMP library path; Docker included its native Linux runtime. The default Docker image did not include PyTorch; neural verification used the local Python environment.

## 7. FAKE / PLACEHOLDER IMPLEMENTATIONS

1. **Reproduced hard-coded UI result:** [Quality.tsx:119](../frontend/src/pages/Quality.tsx) contains `["Required columns", "All 5 present"]`. A real two-column upload with synthesized IDs and all price values absent displays that statement. This is a small but real misleading implementation. The actual validation engine is not mocked.
2. **Incomplete multi-SKU optimization:** the batch endpoint calculates independent policies. There is no shared purchasing-budget decision variable, shared capacity constraint or joint objective. The broad phrase “multi-SKU optimization” must retain that limitation.
3. **Historical overstatements:** older Phase 3 completion language and old measured reports do not establish current full completion. Current README correctly states the joint-allocation limitation. The receipt-timing and catalog issues identified in the older audit have been fixed and were independently rechecked here.

No hard-coded WAPE, fabricated forecast output, arbitrary percentage-based P10/P90, empty required API, mock inventory recommendation, fake safety-stock calculation or fake Monte Carlo engine was found in the inspected application paths.

Normal defaults are not fake outputs: the 80% nominal P10/P90 interval, 95% target service, random seeds, model hyperparameters and risk thresholds are configuration/definitions. Actual metrics and outcomes are computed. Abstract `pass` methods are implemented by concrete models. Test mocks are confined to tests. The 1,000-location performance experiment explicitly reuses one forecast and does not claim 1,000 independently trained models. The separate 500-series catalog contains real distinct histories and model artifacts.

Forecast-quantile interpolation does extrapolate bounded tails above P90 when that explicit sampling mode is chosen. This is an assumption, not a native calibrated P95/P99 forecast. Residual bootstrap also cannot invent unseen tail events. Neither method establishes guaranteed high service levels.

## 8. WHAT NEEDS TO BE DONE NEXT

1. **Priority 1 — Correct the small Phase 1 quality-display defect.** Derive the message from actual required fields/mappings and add a focused regression for optional price and synthesized identifiers. No forecasting rewrite is needed.
2. **Priority 2 — Complete shared-resource Phase 3 optimization.** Specify the joint purchasing-budget/capacity objective and input units; implement allocation across independently forecast SKUs with MOQ/order multiples and transparent infeasibility handling. Connect it through API, dashboard and portfolio tests. This is the substantive missing Phase 3 capability under the broader interpretation of multi-SKU optimization.
3. **Priority 3 — Validate operational calibration and service.** Use representative demand, lead-time, receipt, cost and stockout data to compare nominal coverage/targets with achieved coverage, fill and cycle service. Retain the distinction among these measures.
4. **Priority 4 — Keep status and evidence current.** Make the new findings easy to find, preserve historical reports as dated evidence, and retain coverage for receipt timing, catalog registration, empty costs and UI truthfulness.

No Phase 4 work is required or included. This audit did not implement the listed fixes or add application features.

## 9. FINAL SUMMARY

Phase 1 supports working ingestion, validation, EDA, causal features, four baselines, all five metrics, persistence, APIs, Docker and dashboards. Its only reproduced checklist defect is the inaccurate required-columns message, so strict full-completion status is PARTIAL.

Phase 2 implements real statistical/tree/neural forecasting with fallback, chronological tuning/backtesting, champion selection, empirical P10/P50/P90, probabilistic metrics, TreeSHAP, independent series and saved artifacts. All listed functional requirements were verified.

Phase 3 already supports saved-forecast inventory calculations, receipt-aware risk, constrained per-SKU replenishment, deterministic/Monte Carlo simulations, cost/service/policy comparisons, ABC/XYZ, what-if workflows, portfolios and UI/API persistence. Joint allocation of shared budgets/capacity remains absent.

ForecastIQ is **READY to continue Phase 3**. There is no need to restart Phase 2 or create Phase 3 from scratch. All **256 existing tests passed**, and the audit found no blocking forecasting prerequisite.
