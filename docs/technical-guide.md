# ForecastIQ technical guide

This guide preserves the detailed implementation notes and historical experiment results.
Start with the [project README](../README.md) for current setup instructions and verification.
Historical workspace ports and test counts below describe the original runs.

ForecastIQ Phase 3 connects statistical, machine-learning and neural demand forecasts
to inventory position, safety stock, replenishment, simulation and cost/service decisions.
Every displayed forecast score and inventory result comes from an actual calculation.

Phase 1 ingestion, quality, EDA, four-baseline forecasting and model comparison remain
available, along with all Phase 2 models, backtests, quantiles, SHAP and persisted artifacts.
The [audit before Phase 3](phase3-audit.md) records the baseline checks and environment
repair. The renewed [completion audit](completion-audit.md) and
[completion report](completion-report.md) verify and close gaps across all three
phases. Operational MLOps and monitoring remain outside this phase.

![Forecast quality dashboard](screenshots/phase2-forecast-quality.png)

## Run with Docker

```sh
cp .env.example .env  # Fresh checkout only; preserve an existing .env.
docker compose up --build -d
docker compose ps
```

Default dashboard: **http://localhost:5173**. API: **http://localhost:8000/docs**.
This workspace uses **http://localhost:5180** and **http://localhost:8010/docs** because
other applications occupy the defaults. Its ignored `.env` preserves those ports.

Compose starts PostgreSQL 16, FastAPI and React served by Nginx. Database, normalized
CSVs and fitted artifacts persist in Docker volumes. Ports bind to localhost; the
backend runs as a non-root user. No external account or credentials are required.

The default build contains statistical and tree dependencies. Add CPU PyTorch for
eligible N-BEATS training with:

```sh
INSTALL_NEURAL=true docker compose up --build -d
```

Set `INSTALL_NEURAL=true` in `.env` to retain this choice on subsequent rebuilds.
Without PyTorch or sufficient history, N-BEATS reports a skip reason while other
candidates continue. `docker compose stop` preserves data; `docker compose start`
resumes the stack. Use `docker compose logs -f backend` to inspect fitting failures.

## Local setup

Tested with Python 3.12 and Node 22. `requirements.lock.txt` pins the core environment;
`requirements.txt` contains supported ranges.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m pip install -r requirements-neural.txt  # Optional N-BEATS runtime.
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

LightGBM needs OpenMP. On macOS, `brew install libomp` supplies it; Docker installs
Linux `libgomp1`. See the [LightGBM installation guide](https://lightgbm.readthedocs.io/en/stable/Installation-Guide.html#macos).
For Linux CPU-only PyTorch, append `--index-url https://download.pytorch.org/whl/cpu`
to the optional install; see [PyTorch setup](https://pytorch.org/get-started/locally/).

```sh
# In another terminal:
cd frontend
npm ci
npm run dev
```

Vite proxies `/api` to port 8000. For the workspace ports, start Uvicorn on 8010 and
run `API_TARGET=http://127.0.0.1:8010 npm run dev -- --port 5180`.

PostgreSQL is preferred; local development defaults to SQLite. Override
`DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/forecastiq` as needed.
Additive Alembic migrations run on startup. Revision `0001_forecasting` adopts existing
Phase 1/2 tables; `0002_inventory` adds inventory plans and simulation/policy runs.
Existing data is preserved. PostgreSQL startup migrations use an advisory lock.
`STORAGE_DIR` controls CSV/artifact storage. Back up database and storage together.

## User workflow

1. Choose **Use Demo Dataset**, or configure **Column names and frequency for your
   CSV** before upload. Time and demand columns map to the canonical schema.
2. Inspect **Data quality** and **Overview**, including missing values and filters.
3. Open **Advanced forecasting**; choose a store/product, horizon and frequency.
4. Optional **Evaluation options** control folds, expanding/rolling history, bounded
   tree search and neural eligibility. The required history length is displayed.
5. Click **Train & forecast**. Inspect the champion, comparison statistics, each
   backtest fold, independent test scores, uncertainty band and quantile table.
6. Explore genuine tree SHAP contributions and selection-history diagnostics.
7. Export CSV, restore a saved run, or train another series and compare its results.
8. Open **Inventory optimization**, select a saved forecast and enter on-hand stock
   and lead time in observation periods. Enter known costs and any existing supply arrivals.
9. **Calculate replenishment** to inspect position, safety stock, reorder point, EOQ,
   risk and practical order quantity. Expand the calculation details and assumptions.
10. Run deterministic or Monte Carlo simulation; compare policies and service targets.
    Edit the inputs and click **Compare inputs as what-if** to compare with the saved plan
    using the same forecast, without training again. Horizon is controlled in Simulation.
11. Import inventory CSV for up to 1,000 rows, filter/sort the replenishment queue,
    inspect portfolio and ABC/XYZ results, and export recommendations. Click a queue row
    to restore its inputs, simulation and policy comparison. Its URL opens the saved plan.

**Demand forecast** and **Model comparison** retain the Phase 1 daily workflow with
7/14/28-day horizons. Weekly/monthly data uses Advanced forecasting. The existing
inventory gap remains an arithmetic summary, not an ordering recommendation.

## Data contract

```csv
date,store_id,product_id,category,units_sold,price,promotion
2025-01-01,STORE_01,SKU_001,Food,34,9.99,0
2025-01-02,STORE_01,SKU_001,Food,41,9.99,1
2025-01-03,STORE_01,SKU_001,Food,52,8.99,1
```

| Field | Contract |
|---|---|
| `date` | Calendar date without time of day; daily, a consistent weekday, or month starts/ends |
| `store_id`, `product_id` | Nonempty strings; leading zeros preserved; `sku_id` accepted as a product alias |
| `units_sold` | Nonnegative finite demand; missing observations reported explicitly |
| `price` | Optional; observed values must be finite and positive; missing price leaves revenue unavailable |
| `category`, `region` | Optional dimensions for EDA |
| `promotion`, `holiday`, `discount` | Optional binary indicators / discount fraction in [0, 1] |
| `inventory` | Optional nonnegative snapshot for the existing inventory-gap display; excluded from model features |

Map custom time/target/store/product names before upload. For a single series without
identifiers, enter `__single__` for the absent store or product column. Price can also
be mapped. Select up to 20 additional numeric predictors by comma-separated column
names in the upload controls (`external_features` in the API). They are validated,
persisted and used by linear regression, LightGBM and XGBoost. Reserved target,
identifier and engineered feature names cannot be selected. Unselected additional
columns are not assumed to be predictors.

Frequency inference considers each series separately: month-start/end patterns,
then aligned weekly observations, otherwise daily. Automatic weekly/monthly inference
needs at least three timestamps. Explicit frequency resolves ambiguous sparse data.
Weekly anchors and month-end leap years are preserved. This does **not** aggregate
daily observations into weekly/monthly totals: upload the intended period totals.

Default limits: 25 MB, 1,000,000 uploaded rows, a 10,000-day span per series and 5,000
periods per advanced training request. Exact normalized duplicates are removed and
counted. Conflicting records, invalid dates, negative sales, nonpositive prices,
missing identifiers and malformed CSVs are rejected.

The row limit accommodates the full Kaggle Store Item Demand Forecasting `train.csv`
(913,000 rows). Its `date,store,item,sales` columns are recognized automatically with
the default upload settings; no manual mapping is required. Existing canonical
columns and custom mappings take priority. Price can remain absent. Upload `train.csv`
for training; `test.csv` and `sample_submission.csv` do not supply historical sales.
The [full Kaggle batch report](kaggle-batch/README.md) contains verified results
for all 500 store–item series and a 45,000-row prediction CSV, with local file locations
and reproduction instructions.
`MAX_DATASET_ROWS` in `.env` controls this limit for local development and Docker; after changing it,
restart the local API or run `docker compose up -d --no-deps backend`.

Missing demand blocks forecasting unless the user explicitly confirms it means zero
sales. Reindexing fills only internal gaps. Prices are forward-filled within a series,
never backfilled. Remaining covariates use training-only median imputation (all-empty
features use zero). EDA uses observed data and identifies partial revenue. Overview
shows mean/median demand, sample volatility/CV, a calendar-based trend slope,
MAD outliers and seasonal evidence. Missing periods remain explicit; the descriptive
statistics do not silently impute them. Date filters retain the uploaded frequency.

The bundled **synthetic** demo contains 4,380 daily rows, two stores, six products and
365 observations per series in 2025. Regenerate with `python scripts/generate_demo.py`.
It is not a real retail benchmark.

## Architecture

```mermaid
flowchart LR
  CSV[CSV or synthetic demo] --> V[Mapping and validation]
  V --> DATA[Normalized CSV storage]
  V --> DB[(PostgreSQL metadata)]
  DATA --> LEGACY[Preserved Phase 1 workflow]
  DATA --> SERIES[Selected series and calendar frequency]
  SERIES --> FOLDS[Rolling selection folds]
  FOLDS --> MODELS[Baselines / statistics / trees / N-BEATS]
  MODELS --> SELECT[Aggregate ranking and bounded tuning]
  SELECT --> CAL[Separate residual calibration]
  CAL --> TEST[Untouched test accuracy and quantile metrics]
  TEST --> REFIT[Production refit]
  REFIT --> ART[Models, calibrator and integrity manifests]
  REFIT --> SHAP[Native TreeSHAP]
  ART --> API[FastAPI forecasts and saved results]
  SHAP --> API
  API --> DB
  API --> UI[React / TypeScript / Recharts]
```

| Module under `backend/app/` | Responsibility |
|---|---|
| `data/` | Loading, mapping, validation, frequency preprocessing and diagnostics |
| `features/` | Grouped causal lags, shifted rolling statistics and calendars |
| `forecasting/` | Preserved Phase 1 interface, trainer and predictor |
| `models/` | Phase 2 statistical, tree, neural and baseline implementations |
| `evaluation/` | Chronological plans, metrics, ranking and residual calibration |
| `explainability/` | Exact native TreeSHAP and global/local summaries |
| `services/` | Training orchestration and server-owned model artifacts |
| `api/`, `schemas/`, `db/` | HTTP contracts, validation and persisted records |

`frontend/` holds the dashboard and browser tests; `scripts/`, `tests/` and `docs/`
contain reproducible experiments, verification and measured reports.

Models are **independent per series and trained on demand**. Fold boundaries,
missing-data policies and explanations remain attributable to the selected history;
the platform does not automatically fit heavyweight models across the catalog.
A pooled global model would suit a larger aligned catalog; it is not implemented.
Series comparison exposes each horizon, frequency and test dates because differing
periods and demand scales limit direct comparisons.

## Models and features

| Model | Implementation and adaptation |
|---|---|
| Naive | Repeat last demand; explicit fallback when validation WAPE is undefined |
| Seasonal naive | Repeat last 7 daily, 52 weekly or 12 monthly periods; short-history fallback |
| Moving average | Mean of final seven periods |
| Linear regression | Training-only imputation/standardization, OLS, recursive forecasting |
| ARIMA | Low-order (1,d,1); training trend heuristic chooses d=0/1; bounded optimizer |
| SARIMA | Seasonal AR(1) only with training-history seasonal evidence; otherwise nonseasonal |
| ETS | Additive damped trend / additive seasonality when supported; simple level otherwise |
| LightGBM / XGBoost | Seeded CPU trees, recursive features, configurable randomized chronological search |
| N-BEATS | Three doubly residual blocks with learned backcast/forecast heads and direct multi-period output |

N-BEATS provides a focused univariate model without TFT's additional covariate and
attention machinery. Each block has three 64-unit fully connected layers. Training
uses contiguous windows, training-only centering/scaling, Adam, gradient clipping and
seed 42. Default training is 12 epochs, configurable from 1 to 30. **Every training
fold needs 512 periods**. This compact CPU model is not the paper's large ensemble;
no published benchmark performance is claimed. See the [N-BEATS paper](https://arxiv.org/abs/1905.10437).

Supervised features include period lags **1/2/3/7/14/28**, rolling means and sample
standard deviations **7/14/28**, weekday, day of month, ISO week, month, quarter,
year, weekend, current/lagged price and price changes, supplied event flags and
explicitly selected additional numeric predictors. Both baseline and advanced
supervised paths include all listed lag and rolling features.
Target-derived rolling windows always start with `shift(1)` and never cross series.
Every imputer/scaler fits only on its origin's training history.

Recursive prediction receives no holdout frame: future price stays at the last known
value, future event/discount flags are zero, additional numeric predictors stay at
their last observed training value, and generated demand becomes the next lag.
Missing price uses training-only imputation as a model placeholder; it never creates
a business price or revenue. Planned future covariates are not accepted yet.
Negative predictions are clipped
consistently during evaluation and forecasting. These assumptions can limit accuracy
around promotions, price changes and stockouts.

## Backtesting, tuning and selection

For horizon `h` and `k` folds, reserve the last `h` periods for final test and the
preceding `max(20, 2h)` for calibration. Before them, evaluate `k` consecutive
fixed-origin validation blocks of length `h`. Initial training needs 60 periods:

`minimum history = 60 + (k + 1) × h + max(20, 2h)`.

Horizons support 1–90 periods and folds 2–5. Expanding history is the default;
optional rolling windows retain the requested 60–5,000 periods at every origin.
There is no shuffle or random K-fold validation. Earlier validation observations
can enter later origins, matching information that would then be available.

Each candidate/configuration must finish every fold. Every fold calculates MAE,
RMSE, WAPE, sMAPE and training-scaled MASE. Summaries retain mean, median, sample
standard deviation, best/worst fold and count of defined values for every metric.

Seeded randomized search uses scikit-learn ParameterSampler to draw bounded
LightGBM/XGBoost configurations without replacement. The default is four trials per
tree model; choose 1–10 trials and a seed in Evaluation options. Every candidate uses
the same chronological folds. Disabling tuning fits one fixed configuration.
Parameters, search seed/method, validation scores and durations are retained.
Ranking uses **mean WAPE across all folds**, then WAPE variability, sMAPE, MASE,
normalized forecast step change and model name for deterministic ties. Baselines
can win. All-zero validation uses an explicitly labelled naive fallback. Failed
candidates retain their reasons instead of fake scores.

Tuning and selection finish **before calibration and test**. Calibration/fitting
failures try the next already-ranked candidate without comparing test scores.
Only the selected model is scored on final test. Then production artifacts are
refitted using all available history, or the selected rolling window. A production
refit failure is reported as an error, without retuning against test performance.

## Probabilistic forecasting and metrics

The champion predicts the separate calibration block prequentially: train only on
observations preceding each origin, forecast up to `h` periods, and record signed
residuals `actual − prediction`. Earlier calibration observations may enter later
origins. At least 20 residuals are pooled across forecast leads.

Sorted residual order statistics give P10/P90 offsets at ranks based on
`floor((n+1) × .1)` and `ceil((n+1) × .9)`, clipped to available ranks. The median
residual provides P50 bias correction. Add offsets to point predictions and clip at
zero. This preserves **0 ≤ P10 ≤ P50 ≤ P90** without arbitrary percentage bands.
No final-test residual contributes to these offsets.

These are empirical **marginal** residual quantiles with finite-rank correction,
not distribution-free time-series coverage guarantees. Dependence, pooled horizons,
distribution shifts, small samples and refitting can cause undercoverage. The UI
measures coverage on untouched test observations. Summing period medians does not
produce a calibrated quantile of total demand.

| Metric | Definition |
|---|---|
| MAE / RMSE | Mean absolute error / square root of mean squared error |
| WAPE | `sum(abs(y − p)) / sum(abs(y))`; null for zero actual demand |
| sMAPE | `mean(2 × abs(y − p) / (abs(y) + abs(p)))`; zero/zero contributes zero |
| MASE | MAE / mean seasonal-naive absolute error on pre-origin training history; null for unavailable/zero scale |
| Pinball at q | `mean(max(q × (y − p), (q − 1) × (y − p)))`, q=.1/.5/.9 |
| Coverage | Fraction satisfying `P10 ≤ actual ≤ P90` |
| Mean interval width | `mean(P90 − P10)` in demand units |

WAPE, sMAPE and coverage are fractions in the API and percentages in the UI.
Final point scores evaluate calibrated P50; selection folds evaluate uncalibrated
candidate predictions. The dashboard labels that distinction.

## Explainability and diagnostics

Both tree libraries provide **exact native TreeSHAP**. Global importance is mean
absolute contribution over up to 200 recent production-training rows; dependence
summaries show 40 sample rows. Each forecast date has feature values, signed
contributions and an expected value. The pipeline verifies that their sum
reconstructs the raw tree prediction. References: [LightGBM contributions](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRegressor.html)
and [XGBoost prediction](https://xgboost.readthedocs.io/en/latest/prediction.html).

Contributions apply before clipping and residual calibration. A candidate explanation
is labelled separately from a champion explanation. Effects are relative to the
model's expected value, not causal claims or changes from yesterday. Correlated
lags can share attribution.

Selection-history diagnostics include a trend heuristic, seasonal lag evidence,
ACF/PACF, missing periods and robust MAD outlier flags. Constants omit undefined
correlations; outliers are retained. These are descriptive heuristics, not mandatory
significance tests. Model adaptation recomputes diagnostics within each training fold.

## Actual measured results

The [completion report](completion-report.md) adds a verified 30-period ETS
example: 14.449% untouched-test WAPE, 80% interval coverage, saved inventory results,
and a separate successful N-BEATS training/reload check. Its
[full results](completion-measured-results.json) were generated on 2026-10-05.
The Phase 2 results below preserve the earlier 28-period experiment and tuning setup.

Local run: **STORE_01 / SKU_001**, 365 daily observations, horizon 28, three expanding
folds. The [measured report](phase2-measured-results.md) and
[complete JSON](phase2-measured-results.json) contain every fold, trial and forecast.

| Model | Mean rolling WAPE | Mean sMAPE | Mean MASE | Mean RMSE |
|---|---:|---:|---:|---:|
| **XGBoost — champion** | **12.605%** | 12.657% | 0.6806 | 6.2221 |
| LightGBM | 13.057% | 13.098% | 0.7008 | 6.3860 |
| Linear regression | 14.106% | 14.447% | 0.7509 | 7.0670 |
| ETS | 15.086% | 15.636% | 0.7988 | 7.4775 |
| Moving average | 15.563% | 15.589% | 0.8367 | 7.5460 |
| Seasonal naive | 16.365% | 17.045% | 0.8768 | 8.1213 |
| SARIMA | 17.777% | 17.516% | 0.9458 | 8.0733 |
| ARIMA | 19.412% | 18.872% | 1.0281 | 8.5594 |
| Naive | 25.719% | 29.113% | 1.3414 | 10.9682 |
| N-BEATS | Skipped: insufficient training history | — | — | — |

Final untouched test: **2025-12-04 through 2025-12-31**, calibrated XGBoost P50:

| Metric | Actual result |
|---|---:|
| MAE / RMSE | 8.3231 / 9.7956 |
| WAPE / sMAPE / MASE | 24.583% / 27.058% / 1.1783 |
| P10 / P50 / P90 pinball loss | 2.892244 / 4.161544 / 1.107138 |
| P10–P90 coverage | 89.2857% |
| Mean interval width | 34.942892 units |

Targets WAPE <15%, sMAPE <18%, MASE <0.9 were **not met on this final test**. Coverage
was within the requested 80–90% range. A separate 700-period synthetic example
actually trained N-BEATS (8.633% mean rolling WAPE); XGBoost still won. Its distinct
test scores appear in the report. Browser verification also retains a 7-period run
where recursive linear regression performs poorly on final test.

```sh
python -m scripts.run_phase2_experiment --include-neural
```

This runs real HTTP training, saved-model prediction and CSV export in temporary
SQLite storage, then rewrites measured JSON/Markdown. Omit `--include-neural` for
core-only execution. Timing is one local observation, not a performance guarantee;
floating-point results can vary by platform. The README table records the checked-in
run. Normal API model artifacts remain persisted after training.

## API and artifacts

Direct API paths below use an `/api` prefix through the frontend proxy.

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | API/database readiness |
| POST | `/datasets/demo`, `/datasets/upload` | Demo / multipart CSV ingestion |
| GET | `/datasets`, `/datasets/{id}`, `/datasets/{id}/options` | Reports and available series |
| GET | `/analytics/{id}` | Filtered EDA |
| POST / GET | `/forecast`, `/forecasts/{run_id}` | Preserved Phase 1 forecasting / retrieval |
| POST | `/forecast/train` | Train, backtest, calibrate, evaluate and save |
| POST | `/forecast/predict` | Load champion/calibrator and return dated quantiles |
| GET | `/forecast/runs/{run_id}` | Full saved advanced result |
| GET | `/forecast/models?dataset_id=…` | Saved runs and available artifacts |
| GET | `/forecast/model-comparison?run_id=…` | Aggregate scores, ranks, trials and failures |
| GET | `/forecast/backtest?run_id=…&model=…` | Folds, predictions and summaries |
| GET | `/forecast/explainability?run_id=…&model=lightgbm` | Native tree SHAP |
| GET | `/forecast/export/{run_id}` | CSV: `date,p10,p50,p90` |
| POST | `/forecast/series-comparison` | Latest saved runs for 2–4 independent series |

```sh
curl -X POST http://localhost:8010/datasets/demo
curl -X POST http://localhost:8010/forecast/train \
  -H 'Content-Type: application/json' \
  -d '{"dataset_id":"<dataset-id>","store_id":"STORE_01","product_id":"SKU_001","horizon":28,"folds":3,"window":"expanding","frequency":"auto","tune":true}'
curl -X POST http://localhost:8010/forecast/predict \
  -H 'Content-Type: application/json' -d '{"run_id":"<run-id>"}'
curl 'http://localhost:8010/forecast/backtest?run_id=<run-id>&model=xgboost'
curl -X POST http://localhost:8010/datasets/upload \
  -F 'file=@monthly.csv' -F date_column=period -F target_column=demand \
  -F store_column=shop -F product_column=sku_id -F frequency=monthly
```

Forecast points have `{date, p10, p50, p90}`. Training also returns champion,
configuration, folds, test/probabilistic metrics, boundaries, diagnostics, calibration
records, SHAP, assumptions and timing. Prediction includes `evaluation_metrics` and
`probabilistic_metrics`. Shorter prediction horizons are allowed; longer ones require
a newly evaluated and calibrated run.

Artifacts: `STORAGE_DIR/artifacts/<run-id>/<model>.joblib` plus JSON manifests.
Metadata includes name/version, timestamp, features, horizon, frequency, training
dates, dataset SHA-256, seed, package versions, tuned/fitted parameters, backtest
metrics, tuning duration and production-fit duration. The calibrator is persisted too.
Hashes detect corruption before loading; they do not authenticate a maliciously
replaced file/manifest pair. Only server-generated artifacts are accepted, never
user-uploaded pickle/joblib files.

Errors contain an actionable `error` message: 422 for invalid data/configuration,
404 for unknown records, 409 for unavailable/corrupt artifacts, 503 for DB failure.
One advanced run executes at a time per process; simultaneous training receives
409. FastAPI uses a worker thread so other dashboard requests remain responsive.

## Verification and completion

Latest verification on **2026-10-05**: **219 Python tests passed locally;
16 browser workflows passed** against the running PostgreSQL app, including default
Kaggle column recognition. The original 913,000-row `train.csv` also uploaded through
the browser with unchanged default mappings. Ruff,
TypeScript, the production build and formatting of the completion frontend files
passed. See the [completion report](completion-report.md) for measured examples,
workspace-specific commands, the resolved local OpenMP issue and remaining limits.

```sh
python -m pytest -q
ruff check backend scripts tests
cd frontend
npm run build
npx playwright install chromium
npm test
# Against the running workspace Docker app:
E2E_EXTERNAL=1 E2E_BASE_URL=http://127.0.0.1:5180 npm test
```

Playwright otherwise starts local API/Vite servers on 8000/5173 and refuses to reuse
an unrelated server. `CAPTURE_SCREENSHOTS=1` refreshes real browser captures.
Tests cover model fitting/fallback, leakage-sensitive features and holdouts,
chronology, hand-calculated metrics, quantile order, selection, SHAP reconstruction,
serialization, frequency handling, API persistence, mapping, browser exports and
mobile layout. Delayed-response checks ensure saved runs cannot overwrite newer
selections and series comparisons cannot display an earlier pair's results.
PyTorch tests explicitly skip if the optional runtime is absent;
the recorded full local suite includes actual neural training.

- [x] Phase 1 audited, duplicate-reporting bug fixed, workflow retained.
- [x] ARIMA/SARIMA/ETS, LightGBM, XGBoost and N-BEATS with documented fallback.
- [x] Causal features, expanding/rolling backtests and bounded time-series tuning.
- [x] Aggregate comparison and champion selection independent of final test.
- [x] P10/P50/P90, pinball, coverage and interval width.
- [x] Native SHAP and trend/seasonality/ACF/PACF/missing/outlier diagnostics.
- [x] Configurable daily/weekly/monthly horizons and independent series forecasts.
- [x] Artifacts, API prediction/retrieval, dashboard, saved runs and CSV export.
- [x] Automated verification, actual measured examples and documentation.

See [verification evidence](phase2-verification.md) and the
[complete Phase 2 file inventory](phase2-files.md). Historical Phase 1
[documentation](phase1-README.md), [results](measured-results.md) and
[file inventory](files-created.md) remain available.

## Remaining limitations and later phases

No requested Phase 2 functional item is intentionally left as a placeholder.
The retail demo misses point-accuracy targets. Calibration is marginal and pooled
across leads, with no guaranteed temporal coverage. N-BEATS requires optional
PyTorch and sufficient history. Search budgets are intentionally small; further
improvement needs new validation, not parameter choices driven by final test.

There is no global/hierarchical reconciliation, cold-start model, future-covariate
upload, censored-demand correction, irregular/intraday frequency or joint demand
distribution. Training is synchronous and in memory without a durable job queue;
leaving the page aborts browser delivery, not an already-running server fit.
Saved results include detailed explanations, so storage grows with runs.

This local portfolio application has no authentication, tenant isolation or deployment
migrations. Web fonts fall back to system fonts offline. Safety stock, reorder points,
Phase 3 below adds EOQ, service/cost policy comparison and inventory simulation.
Production MLOps, monitoring and automated retraining remain out of scope.

## Phase 3 — inventory optimization

[Full methodology and formulas](phase3-methodology.md) ·
[Receipt timing and catalog update](phase3-continuation-2026-10-13.md) ·
[Measured walkthrough](phase3-measured-results.md) ·
[Verification and limitations](phase3-verification.md) ·
[Created/modified files](phase3-files.md)

![Inventory decision workspace](screenshots/phase3-inventory.png)

Inventory position is **on-hand + on-order − backorders**. Base lead-time demand sums
saved P50 values over the supplier lead time in days/weeks/months. Reorder point is base
lead-time demand + safety stock. Safety stock supports no buffer, `z σd √L`,
`z √(L σd² + μ² σL²)`, or a requested quantile of sampled aggregate lead-time demand.
Service levels 90%, 95%, 97.5% and 99% are selectable; the API accepts [.5,1).

EOQ is `√(2 Dannual Corder / Hannual)`, using explicit annual demand and costs, with
optional explicit annualization or holding-rate inputs. Practical orders apply the
reorder trigger, target coverage, EOQ when available, MOQ, multiples and an optional
position cap. A non-triggered plan recommends zero. Missing costs yield null with a reason.

Risk uses each period's demand and scheduled receipts over sampled lead time, with at least
one period because replenishment review follows demand. The stockout probability is the
fraction of paths with a supply deficit: high above 50%, medium above 10%, low otherwise.
Late receipts cannot erase earlier shortages. Unscheduled on-order stock is conservatively
excluded from risk, while inventory position still includes it. P50/P90 shortages describe
the immediate stock needed to avoid a deficit, not simulated lost sales. `expedite_quantity`
is that shortfall at the selected service quantile; review transfers or earlier receipts
separately from the purchase-order quantity. Coverage is physical stock / forecast mean.
Optional revenue-at-risk is a shortage scenario times supplied selling price, not profit.
Previously saved plans must be recalculated to use receipt-timing checks; the UI flags them.

Monte Carlo resamples centered held-out forecast errors with configurable circular blocks,
or uses explicitly selected P10/P50/P90 interpolation with bounded extrapolated tails.
Joint lead-time quantiles come from aggregate paths, never sums of marginal P90s. Variable
lead times use a rounded Gamma approximation with supplied moments. Forecast coverage
must include all sampled lead-time exposures; tails are not silently cut off.

Simulation receives supply, clears old backlog, observes demand, reviews inventory and
places constrained replenishment. It supports lost sales/backorders, fixed P50 or 100–1,000
stochastic paths, cost and inventory distributions, fill rate, period service, completed-cycle
service, lost units and turnover only when COGS is supplied. Total operating cost is holding
+ ordering + shortage; purchasing cost and profit are excluded.

Policy selection minimizes **simulated expected total cost subject to minimum mean fill rate**
over an explicit finite candidate set, using common random numbers. Higher safety-stock
targets are not automatically better; missing costs/infeasibility can prevent a recommendation.
ABC uses annual consumption value and cumulative thresholds; XYZ uses configurable historical
CV thresholds. Portfolio totals disclose missing costs/currencies/simulations. Priority sorting
uses risk, immediate supply shortfall, ROP deficit and demand volume, with no hidden score. What-if calculations reuse saved
forecasts. Forecast accuracy and inventory service/cost metrics remain separate.

### Inventory APIs

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/inventory/optimize` | Calculate and persist one inventory plan |
| POST | `/inventory/batch` | Up to 1,000 input rows, cached forecast projections |
| POST | `/inventory/import` | UTF-8 inventory CSV up to 2 MB, row-level results/errors |
| GET | `/inventory/recommendations?dataset_id=…` | Latest plans, filter/sort/paginate |
| GET | `/inventory/plans/{plan_id}` | Plan and latest simulation/comparison |
| GET | `/inventory/sku/{sku_id}?dataset_id=…` | SKU plans across locations |
| POST | `/inventory/simulate` | Deterministic or Monte Carlo simulation, persisted |
| POST/GET | `/inventory/policy-comparison` | Compute / retrieve policy comparison |
| POST | `/inventory/scenario` | Saved-plan what-if and baseline simulations |
| GET | `/inventory/kpis?dataset_id=…` | Latest-plan portfolio KPIs |
| GET/POST | `/inventory/abc-analysis` | Default / configurable ABC and XYZ |
| GET | `/inventory/export?dataset_id=…` | Recommendation CSV |

```sh
curl -X POST http://localhost:8010/inventory/optimize \
  -H 'Content-Type: application/json' -d '{
    "forecast_run_id":"<saved-phase2-run-id>",
    "on_hand_inventory":160,"on_order_inventory":40,"backorders":0,
    "incoming_orders":[{"period":3,"quantity":40}],
    "lead_time":7,"service_level":0.95,"annual_demand":12000,
    "ordering_cost":50,"holding_cost_per_unit_per_year":3.2,"stockout_cost":8,
    "minimum_order_quantity":48,"order_multiple":12,"target_coverage_periods":14
  }'
curl -X POST http://localhost:8010/inventory/simulate \
  -H 'Content-Type: application/json' -d '{"plan_id":"<plan-id>","trials":1000,"seed":42}'
curl -X POST http://localhost:8010/inventory/policy-comparison \
  -H 'Content-Type: application/json' -d '{"plan_id":"<plan-id>","minimum_fill_rate":0.95}'
curl -X POST http://localhost:8010/inventory/scenario \
  -H 'Content-Type: application/json' -d '{"plan_id":"<plan-id>","changes":{"lead_time":3}}'
```

Numbers above are demonstration assumptions, not observed company inventory. A CSV uses
`forecast_run_id,on_hand_inventory,lead_time` and any optional input columns. Existing
Phase 2 forecasts are required for each series; inventory operations never train models.
The advanced and inventory forecast selectors load all pages of saved runs;
`GET /forecast/models` supports `limit` (1–500, default 100) and `offset`.
JSON batch input validation is atomic; valid rows with calculation failures return row
errors alongside successes. CSV validation/calculation errors are row-level except malformed
CSV/arrival JSON. Paged reads and projected JSON fields avoid loading full SHAP/artifact data.

### Register saved catalog forecasts

The offline batch runner writes checkpoints independently of the application database.
Upload its original sales dataset into the app, then register the trusted local catalog:

```sh
python scripts/import_forecast_catalog.py --source storage/kaggle-batch \
  --dataset-id <uploaded-dataset-id> --dry-run
python scripts/import_forecast_catalog.py --source storage/kaggle-batch \
  --dataset-id <uploaded-dataset-id>
```

Use the application's `DATABASE_URL` and `STORAGE_DIR` environment values, or pass
`--database-url` and `--storage-dir`. The database must already be initialized by the app.
For Docker, rebuild the backend to include the CLI, copy the catalog into the backend
container (for example `docker compose cp storage/kaggle-batch backend:/tmp/catalog`),
then run `docker compose exec backend python scripts/import_forecast_catalog.py
--source /tmp/catalog --dataset-id <uploaded-dataset-id>`; use `--dry-run` first.
The container's configured database and storage are used automatically.

Registration checks the selected series' full history and prepared-data fingerprint,
forecast dates/quantiles, calibration chronology and every artifact checksum. It preserves
training timestamps and source provenance, copies artifacts and adds database runs without
retraining. Repeat imports skip matching intact runs; conflicts reject the batch and roll
back new records/files. A process crash may leave an unregistered artifact directory;
the importer refuses to overwrite it, so inspect it before retrying. Original catalog
files are unchanged. Registered forecasts become available to prediction, the inventory
selector, CSV/batch plans and portfolio KPIs. Supply your own operational inventory inputs.

This is a local operator command, not a serialized-model upload API. Only use a catalog
you generated or otherwise trust: checksum verification does not make arbitrary joblib
files safe to load. Runtime package compatibility is checked when a saved model is used.
Multi-SKU plans remain independent; joint budget or shared warehouse-capacity allocation
is not implemented.

Reproduce the saved walkthrough on the running app:

```sh
python -m scripts.run_phase3_experiment --base-url http://127.0.0.1:8010
```

This creates a demo dataset, trains three independent series, calculates real recommendations,
runs deterministic/Monte Carlo/policy/scenario workflows, verifies CSV and formulas, and
writes a timestamped JSON report. The 1,000-location benchmark runs in an isolated temporary
SQLite database; its synthetic locations reuse a real fitted forecast. See the measured
report for actual values, timings, assumptions and the saved-app link.
