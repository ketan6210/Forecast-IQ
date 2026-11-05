# Phase 2 verification

Initial Phase 2 verification completed on 2026-09-27; frontend timing fixes verified
on 2026-09-28. These results describe executed checks, not intended tests.

## Phase 1 audit gate

Before advanced implementation, the original suite passed **89 backend tests**, the
production frontend build passed, and **5 browser tests** passed against Docker with
PostgreSQL. Normalized duplicate counting had one reporting defect. It was fixed and
covered with a regression test; **90 backend tests** then passed before Phase 2 work.
See [the audit](phase1-audit.md).

## Final checks

| Check | Actual outcome |
|---|---|
| Full backend suite, optional PyTorch installed | **137 passed**, 7.00 s; no skips |
| Ruff: backend, scripts, tests | Passed |
| TypeScript + Vite production build | Passed; 2,175 modules transformed |
| Complete Chromium browser suite against Docker/PostgreSQL | **10 passed**, 14.0 s on 2026-09-28 |
| Docker core build/start | Passed; database and API healthy |
| Optional CPU neural Docker build/start | Passed with `torch 2.14.0+cpu` |
| Real HTTP neural example against Docker/PostgreSQL | N-BEATS, both trees and three baselines trained; artifact prediction reproduced quantiles |
| Retail demo experiment with all ten candidates | Nine trained; N-BEATS correctly skipped the short history |
| Long synthetic experiment | N-BEATS trained with three folds; both trees and baselines also evaluated |

The backend emits one upstream Starlette deprecation warning about its current
httpx TestClient adapter. It did not skip or fail a test. Playwright emits a terminal
color-environment warning; there were no uncaught page errors in the advanced workflow.

## Coverage that was exercised

- Original ingestion, validation, missing-data policy, EDA, four baselines, metrics,
  chronological splits, comparison, API persistence, 7/14/28-day forecasts and mobile UI.
- Statistical model fitting/serialization for ARIMA, SARIMA and ETS; actual LightGBM
  and XGBoost fits; actual N-BEATS training and serialization with finite outputs.
- Daily, anchored-weekly, month-start and month-end series; leap-year month ends,
  frequency overrides, internal gaps, explicit zero policy and short histories.
- Expanding and rolling origins with a separate calibration block and untouched test.
- Current/future target perturbations leave earlier lag/rolling features unchanged.
  Changes to calibration/test observations cannot affect tuning, ranks or selection.
  Final-test mutations cannot affect calibration residuals or test predictions.
  Validation covariate mutations cannot affect that fold's fitted preprocessing/predictions.
- MAE/RMSE/WAPE/sMAPE/MASE edge cases, hand-calculated pinball/coverage/width,
  ordered nonnegative quantiles, all-zero demand and explicit undefined metrics.
- Selection based on aggregate performance instead of one lucky fold; failed advanced
  candidates and insufficient neural history leave baseline fallback available.
- Exact SHAP contributions reconstruct both tree models' actual predictions.
- Full train → persisted result → saved artifact prediction → CSV export HTTP workflow;
  corruption and invalid artifact names fail cleanly.
- Browser checks verify API-derived displayed scores, mean/std selection, fold selection,
  both tree explanations, 40 rendered SHAP points, SVG interval area, downloads,
  two independently trained series, saved-run restoration and no horizontal overflow
  at a 390-pixel viewport.
- A browser upload maps custom time/target/store columns, preserves `001`/`002` IDs,
  recognizes `sku_id`, and forecasts seven monthly dates with the expected calendar.

## Exact commands and environment

macOS ARM64, Python 3.12.13, Node 22.23.2. Docker used Linux ARM64 and PostgreSQL 16.
Normal setup commands appear in the [README](../README.md). This workspace has Node
outside the default PATH and no Homebrew OpenMP install, so the executed commands
used the already-installed PyTorch OpenMP library:

```sh
DYLD_LIBRARY_PATH=/Users/ketan/Desktop/ForecastIQ/.venv/lib/python3.12/site-packages/torch/lib \
  .venv/bin/python -m pytest -q
.venv/bin/ruff check backend scripts tests
DYLD_LIBRARY_PATH=/Users/ketan/Desktop/ForecastIQ/.venv/lib/python3.12/site-packages/torch/lib \
  .venv/bin/python -m scripts.run_phase2_experiment --include-neural
INSTALL_NEURAL=true docker compose up --build -d
```

From `frontend/`:

```sh
PATH=/private/tmp/node-v22.23.2-darwin-arm64/bin:$PATH npm run build
PATH=/private/tmp/node-v22.23.2-darwin-arm64/bin:$PATH \
  E2E_EXTERNAL=1 E2E_BASE_URL=http://127.0.0.1:5180 CAPTURE_SCREENSHOTS=1 \
  PLAYWRIGHT_BROWSERS_PATH=/private/tmp/forecastiq-browsers npm test
```

The complete suite ran after the frequency edge-case fix. The final browser run
used the rebuilt app with the champion contrast fix, static SHAP scatter and
series-comparison date/forecast columns. Both default and neural Docker builds
were exercised; the current ignored `.env` retains `INSTALL_NEURAL=true`.

## End-to-end measured examples

The [measured Markdown](phase2-measured-results.md) and
[raw JSON](phase2-measured-results.json) were generated by
`scripts/run_phase2_experiment.py` using real application routes in temporary SQLite
storage. The JSON includes every fold/trial, calibration record, forecast, explanation
and artifact manifest. Temporary experiment artifacts are removed on completion;
normal application artifacts remain in the persistent storage volume.

The 28-period retail example selected XGBoost. Final calibrated P50: MAE **8.3231**,
RMSE **9.7956**, WAPE **24.583%**, sMAPE **27.058%**, MASE **1.1783**. Pinball losses
P10/P50/P90: **2.892244 / 4.161544 / 1.107138**. Coverage **89.2857%**; mean width
**34.942892 units**. Point-accuracy targets were missed; coverage was in the requested
range. No test outcome influenced hyperparameter choices.

The separate 700-period synthetic experiment actually fitted N-BEATS, with mean
rolling WAPE **8.633%**. XGBoost still won. Its test WAPE was **11.306%**, sMAPE
**11.880%**, MASE **0.8095**, coverage **85.7143%**. This is a functionality example,
not evidence of real-world superiority.

That same long-series configuration was also sent over real HTTP to the running
Docker API. [Docker neural evidence](phase2-docker-neural.json) records its persisted
run ID, actual model statuses, PyTorch version, artifact metadata and measured scores.
Reloading the saved champion reproduced the returned quantiles.

## Screenshots and limits

Actual Playwright captures: [advanced dashboard](screenshots/phase2-forecast-quality.png),
[mobile](screenshots/phase2-mobile.png), [monthly upload/forecast](screenshots/phase2-monthly.png).
The seven-period screenshot uses its own two-fold experiment; it must not be compared
as though it were the 28-period report. Its recursive linear champion has poor final
test accuracy. Those values remain visible instead of being replaced with better scores.

No Phase 2 functional requirement remains a placeholder. Generalization on real
retail data, nominal coverage under distribution shift, larger neural training and
public-deployment operations are not established by these synthetic local checks.
The README lists modeling and operating limits. Phases 3–5 remain intentionally
unimplemented.

## 2026-09-28: saved-run and comparison timing fixes

A follow-up review reproduced two user-visible timing bugs against the original
Docker frontend, using delayed real API responses:

- A saved run arriving after a store change reset the form to the previous series.
- A comparison arriving after another pair was selected displayed the previous
  pair's rows under the new selection.

The advanced page now cancels superseded restoration/comparison requests and ignores
their responses and errors. Manual restoration shares the request lifecycle with
training and is cancelled on navigation. A new run clears the old comparison pair.
Loading the saved-run list remains independent of automatic restoration, so editing
controls during loading still leaves saved runs available to open deliberately.

Three regression tests in `frontend/e2e/advanced-races.spec.ts` exercise those
behaviors. Both original bugs were observed failing before the change. The final
complete browser suite passed **10 tests in 14.0 s** against the rebuilt frontend
and the existing PostgreSQL API. Docker's TypeScript/Vite production build and
Prettier checks on both touched TypeScript files passed.

Backend/model code and the measured experiment reports did not change in this
follow-up. The **137-test backend result above is from 2026-09-27**, not a new run.
No additional forecast-accuracy improvement is claimed.

Executed from the project root:

```sh
docker compose up --build -d --no-deps frontend
```

Executed from `frontend/`:

```sh
E2E_EXTERNAL=1 E2E_BASE_URL=http://127.0.0.1:5180 \
  PLAYWRIGHT_BROWSERS_PATH=/private/tmp/forecastiq-browsers \
  /private/tmp/node-v22.23.2-darwin-arm64/bin/node \
  node_modules/@playwright/test/cli.js test
/private/tmp/node-v22.23.2-darwin-arm64/bin/node \
  node_modules/prettier/bin/prettier.cjs --check \
  src/pages/Advanced.tsx e2e/advanced-races.spec.ts
```

The temporary local npm installation was missing `lib/cli.js`; Playwright was
therefore invoked through its installed Node CLI. The Docker build used its own
working npm installation. No project dependency or lockfile changes were needed.

Files changed in this follow-up: `frontend/src/pages/Advanced.tsx`,
`frontend/e2e/advanced-races.spec.ts` (new), `README.md`, this verification report and
`docs/phase2-files.md`.
