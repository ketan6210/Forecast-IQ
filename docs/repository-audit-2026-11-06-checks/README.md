# Audit evidence and reproduction

See the [nine-section audit report](../repository-audit-2026-11-06.md). Core execution occurred
November 6, 2026; the supplemental quality-screen reproduction occurred November 7.
The temporary Docker stack was stopped after verification. Its named volumes were retained.
Application source, the existing application database, and original catalog files were not changed.

| Evidence | What it establishes |
|---|---|
| [summary.json](summary.json) | Environment versions and check summary |
| [pytest.xml](pytest.xml), [pytest.log](pytest.log) | 237 existing Python tests passed, zero failures/skips |
| [playwright.json](playwright.json), [playwright.log](playwright.log) | 19 existing Chromium workflows passed against newly built Docker/PostgreSQL |
| [docker-backend.log](docker-backend.log) | Fresh PostgreSQL migrations, app startup and real HTTP traffic |
| [forecast-pipeline.json](forecast-pipeline.json) | Actual model trials, chronological folds, calibration, holdout metrics, forecast and exact artifact reload |
| [neural-pipeline.json](neural-pipeline.json) | 700-period synthetic API run; N-BEATS actually trained; LightGBM selected |
| [inventory-pipeline.json](inventory-pipeline.json) | Replenishment, deterministic/1,000-path simulation, policy search, scenario and three-series portfolio |
| [catalog.json](catalog.json) | All 500 catalog runs and 3,500 binaries validated; idempotent registration, pagination, five sampled reloads, 500 plans |
| [minimal-schema.json](minimal-schema.json) | Two-column input accepted with explicit synthesized IDs and absent optional price |
| [quality-label.json](quality-label.json), [quality-label.png](quality-label.png), [quality-probe.log](quality-probe.log) | Real UI still claims `All 5 present`; additional audit reproduction passed 1/1 |
| [notebooks.json](notebooks.json) | Both notebooks' 11 code cells executed as Python, without rewriting notebooks |
| [pipeline.log](pipeline.log), [audit_pipeline.py](audit_pipeline.py) | Reproducible additional API/calculation/catalog probe and its execution log |

The forecast and neural examples are synthetic. Inventory costs, stock and supply assumptions are
declared demonstration inputs. Existing catalog artifacts are local files excluded from Git;
reproducing the catalog portion requires those files and the original imported dataset.
Five sampled catalog reloads were LightGBM champions; integrity checking covered all 3,500 binaries.
The 1,000-location benchmark reuses one fitted forecast and is explicitly labeled as such.

From the repository root, the Python command used was:

```sh
DYLD_LIBRARY_PATH="$PWD/.venv/lib/python3.12/site-packages/sklearn/.dylibs" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python -m pytest -q \
  --junitxml=docs/repository-audit-2026-11-06-checks/pytest.xml
.venv/bin/ruff check backend scripts tests

DYLD_LIBRARY_PATH="$PWD/.venv/lib/python3.12/site-packages/sklearn/.dylibs" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python docs/repository-audit-2026-11-06-checks/audit_pipeline.py
```

The library-path setting is specific to this macOS workspace. Other installations can use their
normal working Python/OpenMP setup. The audit probe uses fresh temporary SQLite/storage and
removes those temporary copies at exit; its evidence files remain here.

Fresh isolated Docker build/start and teardown:

```sh
BACKEND_PORT=8016 FRONTEND_PORT=5186 \
  docker compose --env-file .env.example -p forecastiq-audit-20261106 up -d --build

# After browser checks:
docker compose --env-file .env.example -p forecastiq-audit-20261106 stop
```

From `frontend/`, using Node 22.23.2 from `/private/tmp/node-v22.23.2-darwin-arm64/bin`
on PATH during the audit (normal compatible Node installations work too):

```sh
npm run build
PLAYWRIGHT_BROWSERS_PATH=/private/tmp/forecastiq-audit-browsers \
  node node_modules/playwright/cli.js install chromium
E2E_EXTERNAL=1 E2E_BASE_URL=http://127.0.0.1:5186 \
  PLAYWRIGHT_BROWSERS_PATH=/private/tmp/forecastiq-audit-browsers \
  PLAYWRIGHT_JSON_OUTPUT_FILE=../docs/repository-audit-2026-11-06-checks/playwright.json \
  node node_modules/playwright/cli.js test --reporter=list,json

# Separate evidence capture of the known UI defect, excluded from existing-suite totals:
PLAYWRIGHT_BROWSERS_PATH=/private/tmp/forecastiq-audit-browsers \
  node node_modules/playwright/cli.js test \
  --config=../docs/repository-audit-2026-11-06-checks/probe.config.cjs --reporter=list
```

The audit-only reproduction intentionally asserts the current misleading label so that it captures
the defect. It must be updated or retired after that label is corrected; it is not an acceptance test
for the desired fixed behavior.
