# Phase 3 inventory methodology

Inventory outcomes are decision-model estimates, distinct from Phase 2 forecast accuracy
(MAE, RMSE, WAPE, sMAPE, MASE) and quantile calibration metrics. A configured 95% safety-stock
target does not imply an observed 95% fill rate. No external business inputs are invented.

## Inputs, units and defaults

Each plan references one persisted Phase 2 run for a dataset/store/product. Product becomes
`sku_id`; location defaults to that store, with an optional warehouse override. Inputs and
results are immutable snapshots; recalculation creates another plan. The queue and portfolio
use the latest plan per dataset/store/SKU/location; old plans remain addressable by ID.

On-hand stock and integer lead time are required and nonnegative. Negative physical stock
is rejected; backorders are a separate nonnegative field. Defaults visible in the UI/API:
on-order=0, backorders=0, lead-time std=0, MOQ=0, order multiple=1, service target=.95,
residual block size=1, uncertainty paths=1,000, seed=42. Blank costs remain null.
Service targets must be in [.5,1); 100% cannot have a finite normal z-score.

Time units follow the saved frequency: D days, anchored W-* weeks, MS/ME months. Lead time,
lead-time std, coverage targets, arrival periods and simulation horizons all use these
observation periods. An existing purchase order arrives at a 1-based `period`; scheduled
quantities must sum to on-order inventory. A positive on-order amount needs this schedule
before simulation. Horizon must fit the saved forecast (up to 90 periods).

## Formulas

Let OH=on-hand, OO=on-order, B=backorders, L=lead time, alpha=target service,
sigma_d=demand std, sigma_L=lead-time std, and mu=mean saved period P50 demand.

- Inventory position: `IP = OH + OO - B`, distinct from physical OH.
- Base lead-time demand: `D_L = sum(P50[1:L])`. The API's
  `expected_lead_time_demand` is this median-based planning proxy, not a claim about the
  mathematical expectation of skewed demand. Sampled aggregate P50 is reported separately.
- Demand-only safety stock: `SS = z(alpha) * sigma_d * sqrt(L)`.
- Demand and lead-time safety stock:
  `SS = z(alpha) * sqrt(L*sigma_d^2 + mu^2*sigma_L^2)`.
- Forecast-based safety stock: `SS = max(0, sampled_quantile(D_L_paths, alpha) - D_L)`.
- No-safety-stock baseline: `SS = 0`.
- Reorder point: `ROP = D_L + SS`; reorder needed when `IP <= ROP`.
- Units below reorder point: `max(0, ROP-IP)`.
- EOQ: `sqrt(2 * annual_demand * ordering_cost / annual_holding_cost_per_unit)`.
- Annual holding cost can be direct or `unit_cost * annual_holding_rate`, never both.
- Coverage: `OH / mean(P50)`; null when mean demand is zero. Labels follow frequency.

Analytical sigma is a supplied override or historical observed sample standard deviation
(ddof=1), requiring at least two observations. This is not forecast-error std; trend and
seasonality can inflate it. Classical formulas assume independent demand periods and
independent demand/lead time. Fixed-lead demand-only mode rejects positive lead-time std.

EOQ needs supplied annual demand, ordering cost and positive annual holding cost. Missing
inputs or zero holding cost produce null with a reason. Annual demand is never inferred
unless `annualize_forecast=true`: mu times 365.25, 365.25/7 or 12. This explicitly assumes the
forecast mean represents a year. EOQ assumes stationary demand and fixed costs, excluding
shortages; it is an order-size candidate rather than the complete policy.

## Practical replenishment

Target position = sum of P50 over target coverage + SS. Coverage defaults to L+1, limited
by the saved horizon, and must cover L. If IP is above ROP, quantity=0 even when EOQ exists.
When triggered, use the largest positive requirement among target-IP, EOQ, MOQ and one
order multiple; round up to a multiple. If target gap, EOQ and MOQ are all zero, quantity=0.
An optional max inventory-position constraint caps the quantity by rounding capacity down.
If the cap cannot accommodate MOQ/one multiple, return zero and a constraint explanation.
This cap constrains inventory position at order placement, not physical warehouse volume.

Risk accounts for receipt timing separately from IP. For each demand path and sampled lead
time, use periods `1..max(1,L)` and compute
`shortfall = max(0, max_t(B + cumulative_demand[t] - cumulative_receipts[t]) - OH)`.
Receipts arrive before demand in their indicated period. Later receipts cannot erase an
earlier deficit. On-order stock without an arrival schedule remains in IP but is excluded
from this risk assessment with an explicit conservative-assumption notice.

The probability is the fraction of sampled paths whose shortfall exceeds numerical
tolerance (1e-9 units): high above 50%, medium above 10%, low otherwise. P50/P90 shortages
are quantiles of these path shortfalls. They measure immediate extra stock needed to avoid
a deficit, not simulated lost sales. `expedite_quantity` is the shortfall quantile at the
selected service level, without purchase MOQ/multiple rounding. It prompts review of
earlier receipts/transfers, and is not added to the purchase-order quantity. The simulator
does not assume this action is executed. Revenue at risk multiplies shortage by supplied
selling price; no margin or profit is assumed. Zero lead time still exposes the first
period because review and immediate replenishment happen after demand.

Priority is transparent lexicographic ordering: high risk, larger immediate supply
shortfall, larger ROP deficit, then larger forecast volume. Saved plans from before these
receipt checks remain immutable; the UI flags them and their portfolio count for
recalculation. Their stored risk classifications must not be treated as updated results.

## Forecast uncertainty

The default resamples Phase 2 held-out, chronologically stored signed forecast errors,
centered by their median, and adds them to each saved P50, clipping at zero. Circular blocks
preserve local error dependence when block size >1. The default block size=1 explicitly
assumes independent errors. At least 20 calibration errors are required. Pooling forecast
leads/refits and reusing errors assumes stable error behavior; it is not a calibrated joint
forecast model and cannot create unseen extremes. It does not refit a model or read artifacts.

An explicit alternative constructs a piecewise-linear inverse CDF through P10/P50/P90:
`Q0=max(0,P10-(P50-P10)/4)` and `Q1=P90+(P90-P50)/4`, with linear interpolation at
probabilities 0,.1,.5,.9,1. Periods are independent. Service levels above 90% rely on these
bounded extrapolated tails, not native calibrated P95/P99. The UI and response expose this.

Demand is aggregated along sampled paths to compute lead-time quantiles. **Marginal P90s
are never summed and presented as a joint P90.** The separate sum-of-period-P90 field is
labeled a scenario total. Draws are seeded and reproducible.

Variable lead times use a nonnegative Gamma with shape `(L/sigma_L)^2` and scale
`sigma_L^2/L`, rounded to whole periods. Supplied moments refer to the pre-rounding variable;
observed sample moments are reported. If any sampled lead-time exposure exceeds the saved
forecast, calculation rejects rather than truncating its tail. Gamma is an explicit approximation,
not a fitted supplier model. Demand and lead times are sampled independently.

These implementation choices are informed by the primary explanations of
[residual bootstrap prediction intervals](https://otexts.com/fpp3/prediction-intervals.html),
[block bootstrapping](https://otexts.com/fpp3/bootstrap.html) and
[NumPy Gamma sampling](https://numpy.org/doc/stable/reference/random/generated/numpy.random.Generator.gamma.html).
The particular finite-horizon inventory approximation and its caveats are ours.

## Simulation, costs and service

For each period: receive scheduled supply, clear old backlog, fulfill current demand,
record missed demand, review IP, place a constrained order and schedule its arrival.
An order placed in period t with lead L arrives before demand in t+L. Zero-lead orders
arrive after the current demand; lost sales cannot be undone. Backorders can be cleared
immediately but do not retroactively improve immediate fill rate. Initial backlog is served
before new demand. Newly unfilled units are either lost or backordered, selectable by the user.

Deterministic mode uses period P50 demand and fixed nominal lead time. Monte Carlo mode
supports 100–1,000 paths; inventory, fill rate and cost distributions have P10/P50/P90.
Reorder point and target remain static across a simulation. Review occurs once per period;
the safety-stock formulas do not automatically add a review-period buffer. Consequently,
simulation can fall below the nominal service target. No terminal penalty or demand beyond
the horizon is invented; late orders remain outstanding.

- Holding = sum(end-of-period OH) * annual unit holding cost / periods per year.
- Ordering = number of orders placed * fixed order cost.
- Shortage = newly unfilled units * supplied shortage unit cost, charged once per unit.
- Total operating inventory cost = holding + ordering + shortage. It excludes purchasing
  cost, margins, discounting, taxes and financing. Partial components are reported; total
  and its distribution require all three costs, including an explicitly supplied zero if intended.
- Fill rate = immediately fulfilled new demand / total new demand, averaged across paths.
  A zero-demand path has fill rate 1 by convention.
- Period service = fraction of periods without newly unfilled demand; stockout rate is its complement.
- Cycle service = fraction of completed receipt-to-receipt cycles without shortages or unresolved
  backlog. Left/right boundary cycles are excluded; no completed cycles gives null.
- Turnover = supplied horizon COGS / average on-hand inventory value, requiring unit cost
  and positive average stock. It is not silently annualized; missing COGS gives null.

## Policy objective and portfolio

Compare no safety stock, classical demand+lead variability, forecast-quantile stock, and
the best costed feasible quantile service candidate from a configurable finite grid
(default .90/.95/.975/.99). All candidates use the same demand/lead draws.

Objective: minimize simulated expected holding + ordering + shortage cost, subject to
mean immediate fill rate >= supplied minimum fill rate, MOQ, multiples and position cap.
The best overall evaluated feasible policy is reported; if costs are missing or every
candidate is infeasible, there is no recommended policy. This is finite candidate search,
not a global optimizer. Safety-stock target service and achieved fill rate are different.
No guarantee or independent holdout validation of the selected inventory policy is claimed.

Portfolio counts are SKU/location pairs. Inventory value needs known unit costs throughout
and a shared currency designation (or consistently unspecified currency units). Expected
portfolio costs require a simulation for every current plan, matching start date, frequency,
horizon, simulation mode and shortage mode, with complete matching-currency costs.
Service means weight series equally.
Mixed currencies are not converted. Marginal cost percentiles are not added into portfolio
percentiles; cross-SKU dependence is not modeled.

ABC ranks annual demand × unit cost by cumulative known value, defaults A=.8/B=.95.
An item crossing a boundary stays in the bucket of its starting cumulative share; zero-value
items are C if any positive total exists, otherwise unclassified. Missing values are excluded
and counted; mixed currencies disable comparable ABC. XYZ uses historical sample CV:
X<=.5, Y<=1, otherwise Z; thresholds are configurable descriptive defaults. Zero mean or
insufficient history is unclassified. The matrix provides context, not automatic advice.

## Hand-checked ledger

What-if analysis takes a saved plan and changed inputs, slices the saved forecast to
the requested horizon, and recalculates both baseline and changed recommendations
before simulation. Coverage or lead-time requirements beyond that horizon are
rejected. It never retrains forecasts or mutates the original plan. Loading a saved
simulation restores its horizon, mode, paths, seed and shortage mode in the UI.

Daily demand 8,8,8; OH=10, L=1; ROP=5, target=15; no EOQ/MOQ constraint.
Annual holding=365.25 per unit (1/day), order cost=2, shortage cost=3:

| Period | Arrivals | Demand | Ending OH | Lost | Placed | Arrival period |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 8 | 2 | 0 | 13 | 2 |
| 2 | 13 | 8 | 7 | 0 | 0 | — |
| 3 | 0 | 8 | 0 | 1 | 15 | 4 |

Holding=9, ordering=4, shortage=3, total=16; immediate fill=23/24; average inventory=3.
The 15-unit last order remains on order. Automated tests check these values directly.
