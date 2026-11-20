# Phase status, shared allocation and demand validation — November 11, 2026

## Current status

| Area | Status | Evidence and remaining scope |
|---|---|---|
| Phase 1 foundation | COMPLETE for the audited scope | The quality page now reports validated mapped fields, explains generated single-series identifiers and optional price, and has two browser regressions. |
| Phase 2 forecasting | COMPLETE for the audited feature scope | Existing workflows remain connected. The demand validation below identifies interval undercoverage; implementation completeness does not establish forecast reliability for a business. |
| Phase 3 inventory features | COMPLETE for the requested shared-allocation scope | Joint budget/capacity allocation is connected to saved plans, API, PostgreSQL, dashboard, restoration and CSV export. Scope is one purchase decision at one location. |
| Operational performance | PARTIALLY VALIDATED | Available historical sales were checked. Observed supplier lead times, fill rate and cycle service remain UNVERIFIED, as requested, because operational records are unavailable. |

This update follows the [November 6 repository audit](repository-audit-2026-11-06.md).
Earlier dated reports describe their original snapshots. This document and the linked
machine-readable results describe the current changes; the earlier evidence is preserved.

## Phase 1 correction

`frontend/src/pages/Quality.tsx` no longer claims “All 5 present.” It displays
“Required fields after mapping: Validated” for accepted validation results and directs
failed validation to the errors. Date and demand are required, identifiers may be generated
for a single series, and price is optional. Browser tests upload price-free CSVs both
with supplied identifiers and with generated identifiers, then inspect the quality page.

## Joint allocation contract

The allocator consumes **1–200 saved inventory plans**, all from the same dataset and
location, with matching forecast start, horizon and frequency. It rejects duplicate
store/SKU/location demand, missing purchase costs, and missing or mixed currencies.
There is no currency conversion. Zero unit cost is valid when explicitly supplied.

At least one constraint must be supplied; a limit of zero is valid:

- **Purchasing budget:** sum of allocated units times the saved unit purchase cost.
  This excludes fixed ordering fees, tax and freight.
- **Available capacity:** sum of allocated units times user-supplied space per unit.
  Capacity is free space reserved for these orders **after existing stock and committed
  receipts**, in one explicitly named unit. Supply positive per-unit space for every
  selected item. No space release from future demand is assumed.

For item `i`, let `m_i` be the order multiple, `n_i` the integer pack count, `q_i=m_i*n_i`
the quantity, and `y_i` a binary order indicator. Let `U_i` be the number of packs fitting
the saved recommendation and any saved maximum inventory-position limit. Let
`L_i=max(1, ceil(MOQ_i/m_i))`; if `U_i<L_i`, only zero can be ordered.

```text
maximize  sum(priority_weight_i * q_i)
subject to:
    L_i * y_i <= n_i <= U_i * y_i
    sum(unit_cost_i * q_i) <= purchasing_budget       [when supplied]
    sum(capacity_per_unit_i * q_i) <= free_capacity   [when supplied]
    n_i nonnegative integer; y_i in {0, 1}
```

Priority defaults to one and is explicit user input between 0.001 and 1,000. A weight of
two values each allocated unit twice as much. This objective maximizes weighted units;
it does not claim to maximize profit, minimize expected shortages, or guarantee service.
Equivalent optima may produce different allocations. Fractional order multiples work;
the integer variable counts packs. Each item is limited to ten million packs.

The implementation uses [SciPy's mixed-integer solver](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html)
with a ten-second solve limit and zero requested relative gap. An optimal status means
optimal under this objective and these constraints. A feasible time-limited result is
explicitly labeled and reports the solver gap when available. Rounded quantities undergo
an independent check of integrality, nonnegativity, order bounds, MOQ, budget and capacity
before persistence. An unusable or infeasible result returns an error without saving.

Allocations are immutable snapshots in `inventory_allocations`, added by Alembic
`0003_allocation` after `0002_inventory`. The snapshot retains request inputs, plan and
forecast references, quantities, costs, remaining resources, status and assumptions.
Original plans and their recurring simulation policies are unchanged. An allocation is
not a purchase order. Expediting late supply remains a separate action. Multi-warehouse
transfers and recurring joint inventory simulation remain outside this implementation.

## Dashboard and API

In **Inventory optimization → Shared budget and capacity**, select a location and saved
plans, enter budget and/or capacity, supply per-item space if capacity is used, and adjust
priorities if needed. The result shows allocated and deferred units, spend, space usage,
constraints and solver status. Use the saved-allocation selector to restore a decision
after reloading; it lists the twenty most recent decisions for the dataset. CSV export
uses the stored decision. The API supports paginated older history.

| Method | Route | Behavior |
|---|---|---|
| POST | `/inventory/allocate` | Validate, solve and save; returns 201 |
| GET | `/inventory/allocations?dataset_id=…&limit=20&offset=0` | List saved decisions |
| GET | `/inventory/allocations/{allocation_id}` | Restore immutable result |
| GET | `/inventory/allocations/{allocation_id}/export` | CSV, with spreadsheet formula protection for identifiers |

Direct backend routes have no `/api` prefix; the dashboard proxy adds `/api`.
Example request (replace dataset and plan IDs with saved IDs):

```json
{
  "dataset_id": "<dataset-id>",
  "purchasing_budget": 36,
  "available_capacity": 18,
  "capacity_unit": "m3",
  "items": [
    {"plan_id": "<plan-1>", "priority_weight": 1, "capacity_per_unit": 2},
    {"plan_id": "<plan-2>", "priority_weight": 2, "capacity_per_unit": 2}
  ]
}
```

The integration/browser fixture uses two actual fitted demo forecasts, unit cost 3 USD,
MOQ 6 and order multiple 3. With the above constraints it allocates **0 and 9 units**,
spends **27 USD**, and consumes **18 m3**. These costs and space requirements are test
inputs, not observed supplier or warehouse measurements.

## Available-demand validation

The [machine-readable report](operational-validation-2026-11-11.json), measured at
**2026-11-11 21:34:22 UTC**, recomputes saved final holdouts from `storage/kaggle-batch/runs`.
Every saved actual is matched to `data/imports/kaggle-store-item-sales.csv` (913,000 rows).
The validator checks source duplicates, finite nonnegative sales, duplicate series,
ordered/disjoint selection-calibration-test partitions, holdout dates and lengths,
and valid quantiles. It does not retrain or change stored model artifacts.

There are **500 daily series × 90 holdout observations = 45,000 predictions**, covering
**October 3–December 31, 2017**. This is historical recorded-sales evidence, not a claim
that the dataset represents current business demand or uncensored lost demand.

| Measure | Observed value |
|---|---:|
| P10–P90 coverage | **73.9133%**, versus nominal 80% |
| Coverage shortfall | **6.0867 percentage points** |
| Actual below P10 | 23.2089% |
| Actual above P90 | 2.8778% |
| Series below nominal 80% coverage | **350 / 500** |
| Median per-series coverage | 74.4444% |
| Per-series coverage range | 35.5556%–96.6667% |
| MAE / RMSE | 8.0916 / 10.5251 units |
| WAPE / sMAPE | 14.8113% / 16.1986% |
| Mean P10–P90 width | 23.4395 units |
| Pinball loss P10 / P50 / P90 | 1.8000 / 4.0458 / 1.8247 |
| Observed supplier lead times | **UNVERIFIED** |
| Observed fill rate | **UNVERIFIED** |
| Observed cycle service | **UNVERIFIED** |

Coverage includes both interval endpoints and is weighted by observations. Full per-series
and per-lead results, source and catalog SHA-256 digests, and unavailable operational
fields are included in the JSON. WAPE uses total absolute error divided by total sales;
sMAPE assigns zero to pairs where actual and predicted sales are both zero.

The interval misses are asymmetric and aggregate coverage is below its nominal level.
This finding does not identify the cause or prove future coverage. No independent-sample
confidence interval is claimed for correlated series and leads. A calibration follow-up
must use a fresh chronological evaluation design; tuning on this test period would make
it unsuitable as an untouched final test.

Supplier order/receipt records, inventory movements, immediate fulfillment and stockout
records were not available. Following the user's instruction, no supplier/service outcome
is inferred from forecasts or synthetic simulations. Observed fill rate and cycle service
remain null in the report.

Reproduce the calculation from the local catalog and source history:

```sh
python -m scripts.validate_operational_performance \
  --catalog storage/kaggle-batch \
  --history data/imports/kaggle-store-item-sales.csv \
  --output docs/operational-validation-2026-11-11.json
```

## Verification

Final check results are recorded in [the evidence directory](phase3-allocation-2026-11-11-checks/README.md).
Python coverage includes exhaustive-search comparison of a small allocation problem,
binding/zero resource limits, MOQ and fractional packs, incompatible scope rejection,
feasibility rechecking, persistence and exports, migration, and demand-report corruption
checks. Browser coverage includes the two quality regressions and allocation creation,
export, reload/restoration, unchanged source recommendations and mobile layout.
