# Phase 3 file inventory

Compared against the SHA-256 snapshot taken before Phase 3. Generated runtime caches,
virtual environments, Docker volumes, node_modules, dist, local .env and test-result traces
are excluded by .gitignore. No original project file was removed.

## Created (32)

- [alembic.ini](../alembic.ini)
- [backend/app/api/inventory.py](../backend/app/api/inventory.py)
- [backend/app/db/migrations.py](../backend/app/db/migrations.py)
- [backend/app/inventory/__init__.py](../backend/app/inventory/__init__.py)
- [backend/app/inventory/analytics.py](../backend/app/inventory/analytics.py)
- [backend/app/inventory/formulas.py](../backend/app/inventory/formulas.py)
- [backend/app/inventory/policies.py](../backend/app/inventory/policies.py)
- [backend/app/inventory/recommendations.py](../backend/app/inventory/recommendations.py)
- [backend/app/schemas/inventory.py](../backend/app/schemas/inventory.py)
- [backend/app/services/inventory.py](../backend/app/services/inventory.py)
- [backend/app/simulation/__init__.py](../backend/app/simulation/__init__.py)
- [backend/app/simulation/demand.py](../backend/app/simulation/demand.py)
- [backend/app/simulation/inventory_simulator.py](../backend/app/simulation/inventory_simulator.py)
- [backend/migrations/env.py](../backend/migrations/env.py)
- [backend/migrations/versions/0001_existing_forecasting.py](../backend/migrations/versions/0001_existing_forecasting.py)
- [backend/migrations/versions/0002_inventory.py](../backend/migrations/versions/0002_inventory.py)
- [docs/phase3-audit.md](../docs/phase3-audit.md)
- [docs/phase3-files.md](../docs/phase3-files.md)
- [docs/phase3-measured-results.json](../docs/phase3-measured-results.json)
- [docs/phase3-measured-results.md](../docs/phase3-measured-results.md)
- [docs/phase3-methodology.md](../docs/phase3-methodology.md)
- [docs/phase3-verification.md](../docs/phase3-verification.md)
- [docs/screenshots/phase3-inventory.png](../docs/screenshots/phase3-inventory.png)
- [docs/screenshots/phase3-mobile.png](../docs/screenshots/phase3-mobile.png)
- [docs/screenshots/phase3-simulation.png](../docs/screenshots/phase3-simulation.png)
- [docs/screenshots/phase3-walkthrough.png](../docs/screenshots/phase3-walkthrough.png)
- [frontend/e2e/inventory.spec.ts](../frontend/e2e/inventory.spec.ts)
- [frontend/src/inventoryTypes.ts](../frontend/src/inventoryTypes.ts)
- [frontend/src/pages/Inventory.tsx](../frontend/src/pages/Inventory.tsx)
- [scripts/run_phase3_experiment.py](../scripts/run_phase3_experiment.py)
- [tests/integration/test_inventory_api.py](../tests/integration/test_inventory_api.py)
- [tests/unit/test_inventory.py](../tests/unit/test_inventory.py)

## Modified (18)

- [.dockerignore](../.dockerignore)
- [.gitignore](../.gitignore)
- [README.md](../README.md)
- [backend/app/db/models.py](../backend/app/db/models.py)
- [backend/app/main.py](../backend/app/main.py)
- [docs/screenshots/dashboard.png](../docs/screenshots/dashboard.png)
- [docs/screenshots/data-quality.png](../docs/screenshots/data-quality.png)
- [docs/screenshots/forecast.png](../docs/screenshots/forecast.png)
- [docs/screenshots/model-comparison.png](../docs/screenshots/model-comparison.png)
- [docs/screenshots/phase2-forecast-quality.png](../docs/screenshots/phase2-forecast-quality.png)
- [docs/screenshots/phase2-mobile.png](../docs/screenshots/phase2-mobile.png)
- [docs/screenshots/phase2-monthly.png](../docs/screenshots/phase2-monthly.png)
- [docs/screenshots/welcome.png](../docs/screenshots/welcome.png)
- [frontend/src/App.tsx](../frontend/src/App.tsx)
- [frontend/src/styles.css](../frontend/src/styles.css)
- [frontend/src/types.ts](../frontend/src/types.ts)
- [requirements.lock.txt](../requirements.lock.txt)
- [requirements.txt](../requirements.txt)

Existing Phase 1/2 screenshots were refreshed by the full browser regression capture.
Their source workflows remain intact. New screenshots include the actual saved walkthrough
and simulation, plus inventory desktop/mobile regression captures.

Environment repair also created the ignored `.python/` interpreter installation and
repointed `.venv`; these machine-local runtime files are not project source.
