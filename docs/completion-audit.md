# Independent completion audit through Phase 3

**Completion update, 2026-10-05:** the partial items below have been verified as
implemented. The [completion report](completion-report.md) records their evidence,
214 passing Python tests locally and in Docker, 15 passing browser workflows, and
[fresh measured results](completion-measured-results.json). This audit retains the
original pre-edit findings.

Baseline before source edits: **187 Python tests passed (9.24 s), 13 browser workflows passed (20.6 s)**; no failures/skips. Ruff passed. One upstream TestClient deprecation warning.

Inspected the full 160-file project inventory, README/relevant phase reports, model/features/evaluation code, APIs, React pages, SQL models/migrations, tests, data and Docker configuration. Runtime storage check found 96 datasets, 54 advanced runs and 11 inventory plans at that instant (browser tests subsequently add isolated demo records). PostgreSQL was at revision 0002_inventory. Reloaded an existing linear-regression artifact, verified its checksum and generated a real one-period prediction; its normalized CSV existed.

The repository is not initialized as a Git checkout. A SHA-256 file snapshot was saved before edits for the final file inventory. Existing documents alone were not accepted as feature evidence.

## Initial implementation matrix

Paths below are relative to backend/app unless a frontend/test location is named. COMPLETE refers to baseline evidence; PARTIAL rows identify concrete work required by this renewed brief.

| Feature | Phase | Initial status | Evidence | Action |
|---|---:|---|---|---|
| CSV/schema mapping | 1 | PARTIAL | data/repository.py, api/datasets.py; mapped upload tests | Remove required price; connect custom numeric predictors |
| Validation/missing/duplicates/history | 1 | COMPLETE | data/loader.py, validator.py, unit/test_validation.py | Preserve checks; extend to selected predictors |
| Daily/weekly/monthly frequency | 1 | PARTIAL | data/frequency.py; weekly/monthly API tests | Preserve declared frequency through filters/training |
| EDA charts/breakdowns | 1 | PARTIAL | api/analytics.py, pages/Dashboard.tsx | Add median/volatility/outliers/trend to Overview |
| Causal lags/rolling/calendar features | 1 | PARTIAL | features/feature_engineering.py; test_features.py | Complete lag 2/3 and std14 in baseline path |
| Leakage protection and chronology | 1 | COMPLETE | splitter.py; perturbation tests; training-only preprocessing | Extend leakage tests to custom predictors |
| Four baselines and five metrics | 1 | COMPLETE | forecasting/*; evaluation/metrics.py; test_models/evaluation | Preserve and rerun |
| Validation comparison and basic API/UI | 1 | COMPLETE | api/forecast.py; trainer.py; workflows.spec.ts | Make price-free forecasting work |
| Docker/config/errors/logs/seeds/tests | 1 | COMPLETE | Dockerfile, compose, config.py, errors.py, timing.py | Rerun final image and browser checks |
| ARIMA/SARIMA/ETS and failure handling | 2 | COMPLETE | models/statistical.py; integration/test_phase2_api.py | Preserve |
| LightGBM/XGBoost | 2 | PARTIAL | models/supervised.py, tree wrappers; actual fit/SHAP tests | Connect selected external numeric predictors |
| N-BEATS and eligibility fallback | 2 | COMPLETE | models/deep_forecaster.py; real neural fit/serialization test | Preserve; validate long-history run |
| Expanding/rolling backtests and summaries | 2 | COMPLETE | evaluation/backtesting.py; advanced_training.py | Preserve disjoint calibration/test partitions |
| Champion selection and model comparison | 2 | COMPLETE | evaluation/model_selection.py; one-lucky-fold test | Preserve WAPE-first ranking and tie-breakers |
| Controlled hyperparameter tuning | 2 | PARTIAL | registry.parameter_grid contains only two fixed configurations | Add seeded randomized candidates evaluated on existing chronological folds |
| P10/P50/P90 and probabilistic metrics | 2 | COMPLETE | ResidualCalibrator; probability metric hand tests | Preserve empirical calibration and honest coverage |
| SHAP/feature importance/drivers | 2 | COMPLETE | explainability/shap_values.py; tree additivity tests | Verify selected predictors appear in real SHAP |
| Trend/seasonality/ACF/PACF/outliers | 2 | COMPLETE | data/diagnostics.py; Advanced dashboard | Expose descriptive summary before training as well |
| Multi-series and horizons | 2 | COMPLETE | store/product selection, series-comparison API; monthly browser flow | Preserve independent-series workflow; optimize saved-run queries |
| Persisted artifacts and metadata | 2 | COMPLETE | joblib+SHA256 manifest; runtime artifact successfully reloaded | Keep older artifacts usable after feature updates |
| Advanced API/dashboard/export | 2 | COMPLETE | api/advanced.py; Advanced.tsx; 5 advanced browser workflows | Expose search budget/seed and predictor assumptions |
| Inventory inputs and forecast integration | 3 | COMPLETE | schemas/inventory.py; services/inventory.py; no-retraining test | Preserve explicit costs/inputs |
| Inventory position and lead-time demand | 3 | COMPLETE | inventory/formulas.py, recommendations.py; frequency tests | Preserve physical/IP distinction |
| Safety stock/service z-score/ROP | 3 | COMPLETE | four methods; manual formulas and quantile aggregation tests | Preserve assumptions |
| EOQ/MOQ/multiples/caps/coverage | 3 | COMPLETE | formulas.py; practical-order and zero-demand tests | Preserve missing-input explanations |
| Risk/shortage/revenue-at-risk | 3 | COMPLETE | sampled aggregate paths; risk and shortage unit tests | Preserve scenario/probability labels |
| Costs and deterministic simulation | 3 | COMPLETE | simulation/inventory_simulator.py; manual cost ledger/conservation | Preserve arrival timing and backlog accounting |
| Monte Carlo and distributions | 3 | COMPLETE | simulation/demand.py; seed and block-dependence tests | Preserve explicit approximation limits |
| Service and policy comparisons | 3 | COMPLETE | inventory/policies.py; feasible-cost objective test | Preserve common random paths and null winner when infeasible |
| ABC/XYZ/matrix and priority | 3 | COMPLETE | inventory/analytics.py; thresholds/currency tests; queue UI | Preserve transparent segmentation |
| Inventory KPIs and portfolio | 3 | PARTIAL | services/inventory.portfolio_kpis | Do not aggregate different shortage modes |
| What-if analysis | 3 | PARTIAL | api/inventory.scenario only sends horizon to simulator | Apply horizon to demand and recommendation calculations too |
| Multi-SKU/batch/import/export | 3 | COMPLETE | inventory APIs, CSV tests; 1000-row benchmark | Preserve bounded rows and cached forecast projections |
| Inventory dashboard/API/persistence | 3 | PARTIAL | Inventory.tsx; real browser workflows; SQL models/migrations | Restore simulation controls with saved result; expose full cost breakdown |
| Calculation explanations and docs | 3 | COMPLETE | result.calculation_details, phase3-methodology.md | Update documentation with findings and new evidence |

Other regular frequencies are limited to daily, anchored weekly, and month-start/month-end; unsupported intraday/irregular calendars are explicitly rejected or flagged, not silently modeled. No Phase 4 infrastructure is planned.
