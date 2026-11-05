# GitHub publication verification

Checks performed on **November 5, 2026** for publication to
[`ketan6210/Forecast-IQ`](https://github.com/ketan6210/Forecast-IQ).

## Current checks

| Check | Result |
|---|---|
| Python unit/integration suite | **237 passed**, zero failed or skipped; 12.17 seconds |
| Ruff (`backend`, `scripts`, `tests`) | Passed |
| TypeScript project build | Passed |
| Vite production build | Passed; 2,176 modules transformed |
| README and technical-guide relative file links | Checked against the publication file set |
| Publication contents | Source, configuration examples, lockfiles, synthetic demo, notebooks, tests, screenshots, and recorded experiment reports |

The Python run emitted one existing Starlette/httpx deprecation warning. No
application-source changes were required for these checks.

## Runtime details

The Python environment used Python 3.12.13 and included optional PyTorch. On this
Mac, the installed scikit-learn distribution provides the OpenMP library needed
by the tree-model dependencies:

```sh
DYLD_LIBRARY_PATH="$PWD/.venv/lib/python3.12/site-packages/sklearn/.dylibs" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python -m pytest -q
.venv/bin/ruff check backend scripts tests
```

The system shell had no standalone Node.js on its PATH. The Node runtime bundled
with the desktop app completed TypeScript checking but could not load Rollup's
native module because of macOS library-signing restrictions. A standalone
Node.js **22.23.2** runtime downloaded to temporary storage completed both checks
using the existing installed frontend dependencies:

```sh
# From frontend/:
/private/tmp/node-v22.23.2-darwin-arm64/bin/node node_modules/typescript/bin/tsc -b
/private/tmp/node-v22.23.2-darwin-arm64/bin/node node_modules/vite/bin/vite.js build
```

On a fresh checkout with Node.js installed normally, use `npm ci` and
`npm run build` as described in the [README](../README.md).

## Scope

This publication updates the project README, preserves the earlier detailed
README as [technical-guide.md](technical-guide.md), strengthens local-file
exclusions, and records these checks. It does not change application behavior.

The Git file set excludes `.env` and its local variants, Python environments,
dependency folders, caches, frontend build/test output, imported source datasets,
databases, and runtime model storage. `.env.example` and the generated synthetic
demo are included. A scan of candidate text files found no common private-key,
GitHub-token, AWS-access-key, or API-token patterns; this is a limited pattern
check, not a general security audit.

The browser suite, Docker image build, and 500-series forecasting experiment
were **not rerun** for this documentation/publication task. Their historical
evidence remains in the repository. In particular, the
[October 13 report](phase3-continuation-2026-10-13.md#verification) records 19
passing Chromium workflows against PostgreSQL, and the
[Kaggle batch report](kaggle-batch/README.md) records the earlier 500-series run.
Those results should not be interpreted as new measurements from this publication.
