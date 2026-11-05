# Phase 2 file inventory

Compared SHA-256 content hashes with the 88-file workspace snapshot taken before the Phase 1 audit. Updated on 2026-09-28 after the saved-run and comparison timing fixes.

**40 created; 27 modified; 0 removed.**

Runtime dependencies, build outputs, caches, databases and generated model artifacts are ignored and excluded. The local ignored `.env` was also updated to keep `INSTALL_NEURAL=true`; existing ports and database settings were retained. PostgreSQL datasets/runs and Docker storage artifacts were created by the executed examples and browser tests.

## Created

- [backend/app/api/advanced.py](../backend/app/api/advanced.py)
- [backend/app/data/diagnostics.py](../backend/app/data/diagnostics.py)
- [backend/app/data/frequency.py](../backend/app/data/frequency.py)
- [backend/app/evaluation/backtesting.py](../backend/app/evaluation/backtesting.py)
- [backend/app/evaluation/model_selection.py](../backend/app/evaluation/model_selection.py)
- [backend/app/evaluation/probabilistic_metrics.py](../backend/app/evaluation/probabilistic_metrics.py)
- [backend/app/explainability/__init__.py](../backend/app/explainability/__init__.py)
- [backend/app/explainability/shap_values.py](../backend/app/explainability/shap_values.py)
- [backend/app/features/advanced.py](../backend/app/features/advanced.py)
- [backend/app/models/__init__.py](../backend/app/models/__init__.py)
- [backend/app/models/base.py](../backend/app/models/base.py)
- [backend/app/models/baselines.py](../backend/app/models/baselines.py)
- [backend/app/models/deep_forecaster.py](../backend/app/models/deep_forecaster.py)
- [backend/app/models/lightgbm_model.py](../backend/app/models/lightgbm_model.py)
- [backend/app/models/registry.py](../backend/app/models/registry.py)
- [backend/app/models/statistical.py](../backend/app/models/statistical.py)
- [backend/app/models/supervised.py](../backend/app/models/supervised.py)
- [backend/app/models/xgboost_model.py](../backend/app/models/xgboost_model.py)
- [backend/app/schemas/advanced.py](../backend/app/schemas/advanced.py)
- [backend/app/services/__init__.py](../backend/app/services/__init__.py)
- [backend/app/services/advanced_training.py](../backend/app/services/advanced_training.py)
- [backend/app/services/artifacts.py](../backend/app/services/artifacts.py)
- [docs/phase1-README.md](../docs/phase1-README.md)
- [docs/phase1-audit.md](../docs/phase1-audit.md)
- [docs/phase2-docker-neural.json](../docs/phase2-docker-neural.json)
- [docs/phase2-files.md](../docs/phase2-files.md)
- [docs/phase2-measured-results.json](../docs/phase2-measured-results.json)
- [docs/phase2-measured-results.md](../docs/phase2-measured-results.md)
- [docs/phase2-verification.md](../docs/phase2-verification.md)
- [docs/screenshots/phase2-forecast-quality.png](../docs/screenshots/phase2-forecast-quality.png)
- [docs/screenshots/phase2-mobile.png](../docs/screenshots/phase2-mobile.png)
- [docs/screenshots/phase2-monthly.png](../docs/screenshots/phase2-monthly.png)
- [frontend/e2e/advanced-races.spec.ts](../frontend/e2e/advanced-races.spec.ts)
- [frontend/e2e/advanced.spec.ts](../frontend/e2e/advanced.spec.ts)
- [frontend/src/advancedTypes.ts](../frontend/src/advancedTypes.ts)
- [frontend/src/pages/Advanced.tsx](../frontend/src/pages/Advanced.tsx)
- [requirements-neural.txt](../requirements-neural.txt)
- [scripts/run_phase2_experiment.py](../scripts/run_phase2_experiment.py)
- [tests/integration/test_phase2_api.py](../tests/integration/test_phase2_api.py)
- [tests/unit/test_phase2.py](../tests/unit/test_phase2.py)

## Modified

- [.env.example](../.env.example)
- [Dockerfile](../Dockerfile)
- [README.md](../README.md)
- [backend/app/api/analytics.py](../backend/app/api/analytics.py)
- [backend/app/api/datasets.py](../backend/app/api/datasets.py)
- [backend/app/config.py](../backend/app/config.py)
- [backend/app/data/loader.py](../backend/app/data/loader.py)
- [backend/app/data/repository.py](../backend/app/data/repository.py)
- [backend/app/data/validator.py](../backend/app/data/validator.py)
- [backend/app/db/models.py](../backend/app/db/models.py)
- [backend/app/forecasting/predictor.py](../backend/app/forecasting/predictor.py)
- [backend/app/main.py](../backend/app/main.py)
- [backend/app/schemas/datasets.py](../backend/app/schemas/datasets.py)
- [docker-compose.yml](../docker-compose.yml)
- [docs/screenshots/dashboard.png](../docs/screenshots/dashboard.png)
- [docs/screenshots/data-quality.png](../docs/screenshots/data-quality.png)
- [docs/screenshots/forecast.png](../docs/screenshots/forecast.png)
- [docs/screenshots/model-comparison.png](../docs/screenshots/model-comparison.png)
- [docs/screenshots/welcome.png](../docs/screenshots/welcome.png)
- [frontend/src/App.tsx](../frontend/src/App.tsx)
- [frontend/src/pages/Dashboard.tsx](../frontend/src/pages/Dashboard.tsx)
- [frontend/src/pages/Quality.tsx](../frontend/src/pages/Quality.tsx)
- [frontend/src/styles.css](../frontend/src/styles.css)
- [frontend/src/types.ts](../frontend/src/types.ts)
- [requirements.lock.txt](../requirements.lock.txt)
- [requirements.txt](../requirements.txt)
- [tests/unit/test_validation.py](../tests/unit/test_validation.py)

## Removed

None.

The original six browser screenshots were refreshed against Phase 2 while preserving the original workflow. The historical Phase 1 README is archived separately. The synthetic demo CSV, its generator and provenance, original notebooks, baseline implementations and Phase 1 measured-result files were preserved.
