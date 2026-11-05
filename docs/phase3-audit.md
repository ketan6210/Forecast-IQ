# Audit before Phase 3

2026-09-28, before changing the architecture:

- **137 backend tests passed** in the existing CPU-neural Docker image, including
  actual N-BEATS training; no skips; one upstream TestClient deprecation warning.
- **10 browser tests passed** against the existing PostgreSQL-backed app (15.3 s).
- Ruff passed on backend, scripts and tests.
- Inspected ingestion/validation, preprocessing, feature construction, chronological
  evaluation, candidate registry, saved-run schemas, artifacts, API routes and UI.

Phase 1 contains all four baseline models, quality/EDA, leakage-sensitive tests,
chronological validation/test metrics and a working preserved browser workflow.
Phase 2 contains ARIMA/SARIMA/ETS, both tree models, optional N-BEATS with actual
training tests, rolling evaluation/tuning, validation-selected champions, separately
calibrated quantiles, probabilistic metrics, native SHAP, calendar frequencies,
independent series, model artifacts and saved-run/export APIs.

There were no missing Phase 1/2 functional placeholders found. Existing results
honestly document accuracy failures and calibration limitations. Saved marginal
quantiles are not joint path quantiles; Phase 3 must not sum upper bounds and claim
aggregate coverage. The existing inventory gap is only arithmetic, not an optimizer.

The local virtual environment was broken because its base interpreter lived in a
removed temporary directory. Restored Python 3.12.13 under the ignored `.python/`
workspace directory and repointed `.venv` while preserving installed dependencies.
The verified Docker runtime allowed the audit suite to run before this repair.
Temporary npm also lacks CLI files; Node can execute installed project CLIs, and
the Docker frontend build retains its own working npm.

The application previously created tables on startup without versioned migrations.
Phase 3 introduces additive Alembic revisions, including safe adoption of the existing
Phase 1/2 schema. Existing datasets, forecasts and model artifacts must be preserved.
