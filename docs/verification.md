# Completed verification

Verified on 2026-09-25. The workspace was initially empty; this implementation
adds Phase 1 only.

| Check | Actual result |
|---|---|
| Backend `pytest -q` | **89 passed**, 1 upstream deprecation warning, 2.42 s |
| Backend Ruff | **All checks passed** |
| Frontend `npm run build` | **Passed**, TypeScript + Vite production build |
| Docker `compose up --build -d` | **Passed**, PostgreSQL and backend healthy, frontend running |
| Browser end-to-end tests against the Docker/PostgreSQL stack | **5 passed**, 9.7 s |
| EDA notebook | All code cells executed successfully |
| Baseline experiment notebook | All code cells executed successfully |

The single backend warning is Starlette's deprecation of its `httpx` test-client
adapter in favor of `httpx2`. It is a dependency warning; no tests failed.

Browser coverage:

1. Demo → quality → EDA filters → actual API forecast values → comparison;
   verified 7-, 14-, and 28-day horizons.
2. Invalid CSV rejection, valid CSV upload, forecasting, and dataset restoration
   after page reload.
3. Mobile navigation and forecasting at 390 × 844, without horizontal overflow.
4. Explicit zero-sales policy remains selected after returning from comparison.
5. Navigating away discards an in-flight forecast response.

The browser suite used real API responses and PostgreSQL persistence. The last
test delays a real response to exercise cancellation; it does not supply invented
model results. Screenshots were captured from the running application and visually
reviewed on desktop and mobile.

## Commands executed

From the repository root:

```sh
UV_CACHE_DIR=/private/tmp/forecastiq-uv-cache uv venv --python python3.12 .venv
UV_CACHE_DIR=/private/tmp/forecastiq-uv-cache uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python scripts/generate_demo.py
.venv/bin/ruff check backend scripts tests
.venv/bin/python -m pytest -q
.venv/bin/python -m scripts.run_experiment
docker compose up --build -d
```

Frontend commands (executed in `frontend/`):

```sh
export PATH=/private/tmp/node-v22.23.2-darwin-arm64/bin:$PATH
npm install --cache /private/tmp/forecastiq-npm-cache --fetch-retries=0
npm run build
PLAYWRIGHT_BROWSERS_PATH=/private/tmp/forecastiq-browsers npx playwright install chromium
E2E_EXTERNAL=1 E2E_BASE_URL=http://127.0.0.1:5180 \
  CAPTURE_SCREENSHOTS=1 \
  PLAYWRIGHT_BROWSERS_PATH=/private/tmp/forecastiq-browsers npm test
```

The existing Node binary was outside the shell's default PATH, so it was explicitly
added for verification. Package installation, Docker socket access, and launching
Chromium required the environment's sandbox approvals. Standard Node/Python/Docker
installations can use the simpler commands in the main README.

The notebook smoke check loaded both `.ipynb` files and executed every code cell
with the project's Python environment. It did not require Jupyter or alter their
unexecuted, reproducible notebook files.

## Running instance

- Dashboard: **http://localhost:5180**
- API and Swagger: **http://localhost:8010/docs**
- Database: Docker Compose PostgreSQL 16 service, no public host port
- Startup: `docker compose up --build -d`
- Stop while preserving data: `docker compose stop`

Local ports 8000, 8001, 5173, and 5174 were already occupied by other applications.
ForecastIQ's ignored `.env` uses 8010 and 5180. Those other applications were left running.

## Measurement provenance and limits

The experiment in [measured-results.md](measured-results.md) was run on 2026-09-24,
using the bundled synthetic data, Python 3.12.13, pandas 2.3.3, NumPy 2.5.3, and
scikit-learn 1.9.1. Metrics, including the poor recursive regression test result,
are preserved as measured. They do not imply real-retail performance.

The final application is a local Phase 1 foundation. There are no confidence
intervals, reorder recommendations, advanced models, monitoring, or automated
retraining. See the main README for the full methodological and operational limits.
