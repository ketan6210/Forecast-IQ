> Historical Phase 1 documentation. See the [current README](../README.md) for Phase 2.

# ForecastIQ — Demand Forecasting & Inventory Optimization Platform

Businesses need accurate demand forecasts to manage inventory. ForecastIQ Phase 1
provides a transparent foundation: load daily sales, assess data quality, explore
demand, and compare four forecasting baselines with chronological evaluation.

**Phase 1 only.** Implemented: CSV/demo ingestion, validation, EDA, historical
features, baseline forecasting, measured model comparison, and a responsive dashboard.
The only inventory calculation is an **Inventory Gap**, not a reorder recommendation.

![ForecastIQ forecast dashboard](screenshots/forecast.png)

## Run with Docker

Requires Docker with Compose. From the repository root:

```sh
cp .env.example .env   # For a fresh checkout; preserve an existing local .env.
docker compose up --build -d
docker compose ps
```

Default addresses: dashboard **http://localhost:5173**, API **http://localhost:8000**,
interactive API docs **http://localhost:8000/docs**. The stack runs PostgreSQL 16,
FastAPI, and a built React frontend served by Nginx. PostgreSQL and uploaded CSVs
use separate persistent Docker volumes. Ports bind to localhost.

**This workspace is already configured on http://localhost:5180 and
http://localhost:8010/docs** because other applications occupied the defaults.
Its ignored `.env` sets `FRONTEND_PORT=5180` and `BACKEND_PORT=8010`.
Running `docker compose up --build -d` preserves those settings.

```sh
docker compose logs -f backend
docker compose stop         # Stops this stack and preserves its data.
docker compose start
```

The example database credentials are development defaults. No external credentials
are needed. `.env`, local storage, dependencies, and test artifacts are ignored.

## Run locally

Tested with Python 3.12 and Node 22. Use Python 3.12+ for the supplied dependency
snapshot. Source syntax supports Python 3.11+, for which `requirements.txt` lets
pip resolve compatible package versions. PostgreSQL is the preferred database;
SQLite is provided only as a local development fallback.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
# On a fresh checkout, copy .env.example to .env if desired.
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

The Vite development server proxies `/api` to port 8000. If ports are occupied:

```sh
# Root terminal
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
# Frontend terminal
API_TARGET=http://127.0.0.1:8010 npm run dev -- --port 5180
```

Use a local PostgreSQL connection with:
`DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/forecastiq`.
The tables are created on startup. `STORAGE_DIR` controls CSV storage.
Compose overrides the SQLite URL with its PostgreSQL service URL.

## Demo walkthrough

1. Open ForecastIQ and click **Use Demo Dataset**, or **Upload CSV**.
2. Review the **Data quality report** and its missing values and warnings.
3. Open the **Overview** for six charts and store/product/category/date filters.
4. Select **Demand forecast**, a store, a product, and **7 / 14 / 28 days**.
5. Click **Generate forecast**. The application trains all four baselines,
   chooses using validation WAPE, evaluates on test, and forecasts from all history.
6. Inspect the requested horizon's total, historical/forecast chart, business
   summary, test metrics, and optional inventory gap.
7. Open **View model comparison**. Switch between validation and final test metrics.

The bundled data is **synthetic**, generated with a fixed seed: 4,380 rows,
2 stores, 6 products, and daily history from 2025-01-01 through 2025-12-31.
It contains annual seasonality, weekend effects, promotions, variable prices,
and illustrative inventory snapshots. It is not real-world benchmark data.

Regenerate it with `python scripts/generate_demo.py`.

## Dataset contract

```csv
date,store_id,product_id,category,units_sold,price,promotion
2025-01-01,STORE_01,SKU_001,Food,34,9.99,0
2025-01-02,STORE_01,SKU_001,Food,41,9.99,1
2025-01-03,STORE_01,SKU_001,Food,52,8.99,1
```

| Column | Contract |
|---|---|
| `date` | Required daily date; use `YYYY-MM-DD`, without a time of day |
| `store_id`, `product_id` | Required nonempty strings; leading zeros preserved |
| `units_sold` | Required column; nonnegative, finite numeric observations |
| `price` | Required column; observed values must be finite and greater than zero |
| `category`, `region` | Optional string dimensions |
| `promotion`, `holiday` | Optional 0/1 indicators |
| `discount` | Optional numeric fraction in [0, 1] |
| `inventory` | Optional nonnegative latest-date inventory snapshot |

Uploads accept UTF-8 CSV, at most 25 MB and 500,000 rows by default. Invalid dates,
negative demand, nonpositive prices, missing identifiers, malformed records,
duplicate column names, and conflicting store/product/date observations are rejected.
Exact duplicate rows are removed with a reported warning. Data is sorted per series.

Missing sales/prices are reported. All-missing sales or prices fail validation.
Each series gets an expected daily date index, limited to a 10,000-day span.
Absent sales remain flagged by default and prevent forecasting. Explicit
`missing_policy: "zero"` is available only when the user confirms that missing
observations mean zero sales. This includes both absent dates and blank sales cells.
It does not fill gaps at the beginning or end beyond the observed series range.

Prices are forward-filled within each series, never backfilled. Remaining unknown
regression covariates use training-only median imputation (all-empty features use 0).
Unknown historical event flags remain missing until that fitted imputer is applied.
EDA uses the observed dataset, without forecast-time zero filling. Revenue is in
the currency of the price column, and is marked partial when price/sales are missing.
Average daily demand in EDA uses days with observed sales, not an assumed complete calendar.

## Architecture

```mermaid
flowchart LR
  CSV[Uploaded CSV or synthetic demo] --> V[DataValidator]
  V --> S[Normalized CSV storage]
  V --> DB[(PostgreSQL metadata)]
  S --> EDA[Filtered analytics]
  S --> P[Per-series daily preprocessing]
  P --> F[Causal calendar / lag / rolling features]
  F --> SPLIT[Chronological train / validation / test]
  SPLIT --> M[Four baseline models]
  M --> SELECT[Select by validation WAPE then MASE]
  SELECT --> TEST[Final test evaluation]
  TEST --> REFIT[Refit selected model on all history]
  REFIT --> FORECAST[7 / 14 / 28 day forecast]
  FORECAST --> DB
  EDA --> API[FastAPI]
  FORECAST --> API
  API --> UI[React + TypeScript + Recharts]
```

```text
backend/app/
  api/          datasets, analytics, forecast routes
  data/         loader, validator, repository, daily preprocessing
  features/     historical feature construction
  forecasting/  model interface, four baselines, trainer, predictor
  evaluation/   metrics, chronological splitter, validation-only selection
  db/           SQLAlchemy datasets and forecast-run persistence
  schemas/      typed dataset and forecast contracts
frontend/       React pages, API client, responsive styles, browser tests
data/demo/      bundled synthetic CSV and its provenance
scripts/        deterministic data generation and measured experiments
notebooks/      EDA and baseline experiments using the same application modules
tests/          backend unit and integration tests
docs/           measured outputs, screenshots, complete file inventory
```

Model extensions implement `ForecastModel.fit(history, features)` and
`predict(horizon)` and register with `MODEL_REGISTRY`. Database records preserve
the selected model, validation metrics, test metrics, request, forecast, comparison,
split dates, assumptions, and timings. Forecast runs are retrievable by ID.

## Forecasting methodology

**Why chronological splitting?** Future sales must remain unseen when evaluating a
forecast. Unique dates are split 70% train, 15% validation, 15% test, with strict
`max(train.date) < min(validation.date) < min(test.date)`. There is no random shuffle.
At least 90 daily observations after the chosen missing-data policy are required.

All four models use the same **fixed-origin, multi-step** holdouts. Fit on train
and forecast the entire validation period without observing its outcomes. Select
by validation WAPE, breaking ties with lower defined validation MASE, then model
name for determinism. If all validation WAPE values are undefined, report that
condition and use naive as an explicit fallback. Test metrics never select a model.

Refit each baseline on train + validation for test evaluation. Finally refit the
selected baseline on all available history for the requested future horizon.
The 15% holdout lengths may differ from the user's 7/14/28-day future horizon.

| Baseline | Multi-step behavior |
|---|---|
| Naive | Repeat the last observed demand |
| Seasonal naive | Repeat the final observed seven-day pattern for every future week |
| Moving average | Use the fixed mean of the final seven observed days |
| Linear regression | Ordinary least squares over calendar, lags, shifted rolling features, price and optional events; recursively append predictions |

**Why seasonal naive?** Retail demand often has weekday structure. Repeating the
most recent week is a transparent reference that stronger models should justify
improving upon. It is evaluated like the other models, not assumed to be best.

Features include weekday, day of month, ISO week, month, quarter, year, weekend;
sales lags 1/7/14/28; shifted rolling means 7/14/28; shifted sample standard
deviations 7/28; current price, previous price, price change and percentage change;
and promotion/discount/holiday when supplied.

**Leakage prevention:** every target-derived rolling window starts with `shift(1)`.
Features are grouped by store/product and sorted by daily date. Lag windows cannot
cross series. There is no future backfill. Regression imputers and scalers fit
only on the history available at each origin. Recursive prediction receives no
holdout actuals or realized future covariates. It uses its own prior predictions,
last known price, and zero future promotion/discount/holiday indicators. Negative
linear predictions are clipped to zero using the same rule during all evaluation.

Explicit tests mutate targets at `t`, `t+1`, `t+2`, and later dates and prove
features through `t` do not change. Another test mutates test targets and covariates
and verifies that all validation metrics and the selected model remain unchanged.

## Metrics

| Metric | Definition and interpretation |
|---|---|
| MAE | Mean absolute error, in units |
| RMSE | Square root of mean squared error, in units; emphasizes larger errors |
| WAPE | `sum(abs(actual - predicted)) / sum(abs(actual))` |
| sMAPE | Mean of `2 * abs(actual - predicted) / (abs(actual) + abs(predicted))` |
| MASE | MAE divided by mean absolute seven-day naive error in pre-origin training history |

**Why WAPE?** It expresses error relative to total demand and is useful for comparing
these models on the same series and validation interval. High-volume observations
contribute more. It can hide errors on low-volume days and is undefined for zero demand.

**Why MASE?** It puts error on a weekly naive historical scale. A value below one
means lower error than that training-history scale; it does not directly assert
that the model beat seasonal naive on the same holdout.

The API returns WAPE and sMAPE as fractions; the UI shows percentages. WAPE is null
when total actual demand is zero. MASE is null for insufficient or zero-error
scaling history. A pair of zeros contributes zero to sMAPE. Undefined values render
as `—`, are excluded from best-value highlighting, and are never replaced with fake scores.

## Actual measured experiment

Measured locally on **synthetic STORE_01 / SKU_001**, with a requested 28-day forecast.
The chosen baseline was **moving average**, based on **12.441% validation WAPE**.
These are final **test** results on 2025-11-07 through 2025-12-31:

| Model | MAE | RMSE | WAPE | sMAPE | MASE |
|---|---:|---:|---:|---:|---:|
| Naive | 6.9273 | 9.1124 | 20.572% | 21.217% | 0.9934 |
| Seasonal naive | 6.4909 | 7.8752 | 19.276% | 19.973% | 0.9308 |
| Moving average | 5.7636 | 7.7682 | 17.117% | 17.140% | 0.8265 |
| Linear regression | 36.3350 | 119.8467 | 107.906% | 37.858% | 5.2104 |

The selected model's future 28-day demand is **864 units**. The regression baseline
is unstable in this long recursive test window; that measured failure is retained,
and no hyperparameters were chosen using test performance.

| Data / system measurement | Actual value |
|---|---:|
| Dataset rows / stores / products | 4,380 / 2 / 6 |
| Dataset period | 2025-01-01 → 2025-12-31 |
| Missing cell rate | 0.00% |
| CSV load + validation | 0.023215 s |
| Feature generation | 0.003641 s |
| Training + holdout evaluation + final refit | 0.376296 s |
| Prediction-only forecast latency | 0.000038 s |
| Entire in-process forecast request, including persistence | 0.396942 s |

One local measurement, not a benchmark or a latency guarantee. Full machine/package
details, both metric partitions, and exact split boundaries are in
[the measured report](measured-results.md) and [raw JSON](measured-results.json).

```sh
source .venv/bin/activate
python -m scripts.run_experiment
```

This reruns the demo in a temporary SQLite database and replaces the report files
with newly measured results. Timings and floating-point regression results can
differ across machines. The checked-in README table records the original measured run.

## API

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | API/database readiness |
| POST | `/datasets/demo` | Ingest the bundled synthetic data |
| POST | `/datasets/upload` | Multipart field `file`, CSV upload |
| GET | `/datasets` | List the 100 most recent datasets |
| GET | `/datasets/{id}` | Persisted metadata and validation report |
| GET | `/datasets/{id}/options` | Stores, products, categories, store/product mapping |
| GET | `/analytics/{id}` | Summary and six chart datasets, with filters |
| POST | `/forecast` | Train/evaluate four baselines and save a forecast run |
| GET | `/forecasts/{run_id}` | Retrieve the complete saved run |

Analytics filters: `store`, `product`, `category`, `date_from`, `date_to`.

```sh
curl -X POST http://localhost:8010/datasets/demo
curl -X POST http://localhost:8010/datasets/upload -F 'file=@data/demo/retail_sales.csv'
curl -X POST http://localhost:8010/forecast \
  -H 'Content-Type: application/json' \
  -d '{"dataset_id":"<returned-id>","store_id":"STORE_01","product_id":"SKU_001","horizon":28}'
```

The forecast response includes `model`, dated `forecast`, `history`, `metrics`
(an alias of final `test_metrics`), `validation_metrics`, `test_metrics`, four-model
`comparison`, `split`, business `summary`, `timings`, `warnings`, and `assumptions`.
`summary.inventory_gap` equals latest-date inventory minus forecast total; it is
null when the latest inventory observation is missing.

Errors use `{ "error": "actionable message", "details": ... }`: 415 for invalid
file type, 413 for size limits, 422 for invalid data/request/history/model fit,
404 for unknown datasets/series/runs or empty filters, and 503 for database failures.

## Verification

```sh
source .venv/bin/activate
python -m pytest -q
ruff check backend scripts tests
cd frontend
npm run build
npx playwright install chromium
npm test
```

`npm test` starts temporary local API/Vite servers on 8000/5173 and refuses to reuse
an unrelated existing server. To test an already-running Docker stack instead:

```sh
cd frontend
E2E_EXTERNAL=1 E2E_BASE_URL=http://127.0.0.1:5180 npm test
```

Set `CAPTURE_SCREENSHOTS=1` on that command to refresh actual browser screenshots.
The end-to-end tests exercise demo ingestion, quality, EDA filters, all horizons,
measured API values in the UI, model comparison, invalid/valid uploads, persistence
across reload, and a 390-pixel mobile viewport.

Backend tests cover validators, malformed CSVs, gap policies, metrics including zero
denominators, grouped features, current/future target leakage, chronological splits,
all models/horizons, validation-only selection, forecast persistence, and error handling.
See [verification results](verification.md) for the completed run results and commands.

## Screenshots

Real screenshots captured by the browser tests:

| Get started | Data quality |
|---|---|
| ![Welcome](screenshots/welcome.png) | ![Data quality](screenshots/data-quality.png) |

| Analytics | Comparison |
|---|---|
| ![Analytics](screenshots/dashboard.png) | ![Comparison](screenshots/model-comparison.png) |

[Mobile forecast](screenshots/forecast-mobile.png)

## Known Phase 1 limitations

- Daily, individual store/product forecasts only. No hierarchical reconciliation,
  pooled models, cold-start forecasts, or guaranteed forecast accuracy.
- A single 70/15/15 fixed-origin experiment, not rolling-origin cross-validation.
  Holdout lengths vary with history length and do not match every requested horizon.
- Recursive unregularized linear regression can amplify errors substantially.
  Future planned prices, promotions and holidays cannot yet be supplied.
- Stockouts and censored sales are not modeled. Recorded sales are used as demand.
- Inventory gap omits lead times, safety stock, incoming orders and service levels.
- Synchronous, in-memory pandas processing and per-request fitting. No task queue,
  persistent fitted model artifacts, model registry, monitoring, or retraining scheduler.
- A local development application: no authentication, multi-tenant isolation,
  database migrations, or public-deployment configuration. Preserve both the
  database volume and CSV volume when backing up.
- Dataset/run metadata persists in the database. The browser remembers its dataset
  selection; its last forecast is not automatically restored after reload, but runs
  remain retrievable through the API.
- Synthetic examples do not demonstrate business performance on real retail data.
  Optional web fonts fall back to system fonts when offline.

## Phase 2 roadmap (not implemented)

Stronger models behind the existing interface, rolling-origin evaluation,
planned future covariates, and calibrated probabilistic forecasts. Inventory
optimization and operational MLOps remain later phases. No LightGBM, XGBoost,
deep learning, LLMs, agents, cloud services, drift detection, or automated retraining
are included in this implementation.

See [the complete created-file inventory](files-created.md) for every project
source, configuration, test, data, notebook, screenshot, and report file.

Implementation references: [Vite setup](https://vite.dev/guide/) and
[FastAPI file uploads](https://fastapi.tiangolo.com/tutorial/request-files/).
