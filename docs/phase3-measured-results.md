# Phase 3 measured walkthrough

Measured: 2026-09-29T02:23:26.152483+00:00

Actual fitted forecasts on bundled synthetic retail history. Inventory quantities, costs and service targets below are explicitly chosen demonstration assumptions; they are not observed company business data.

[Open this saved example in the running app](http://localhost:5180/?dataset=ec0457bc-1616-4264-9576-a87d54b62998&view=inventory&plan=313e01f0-71af-4753-8a98-4e7a567415c5).

Champion: **ets**. Store STORE_01 / SKU_001; 30 daily forecast periods. [Full numeric results](phase3-measured-results.json).

## Declared demonstration inputs

```json
{
  "forecast_run_id": "78c059cd-44d7-4571-a4b9-1e5dc4205b18",
  "on_hand_inventory": 160,
  "on_order_inventory": 40,
  "incoming_orders": [
    {
      "period": 3,
      "quantity": 40
    }
  ],
  "backorders": 0,
  "lead_time": 7,
  "service_level": 0.95,
  "annual_demand": 12000,
  "ordering_cost": 50,
  "holding_cost_per_unit_per_year": 3.2,
  "stockout_cost": 8,
  "unit_cost": 12,
  "selling_price": 20,
  "currency": "USD",
  "minimum_order_quantity": 48,
  "order_multiple": 12,
  "target_coverage_periods": 14,
  "uncertainty_samples": 10000,
  "seed": 42
}
```

## Calculated recommendation

| Measure | Actual value |
|---|---:|
| 30-period P50 scenario sum | 921.671014 |
| 30-period marginal P90 scenario sum (not a joint P90) | 1161.037681 |
| On-hand inventory | 160.000000 |
| Inventory position | 200.000000 |
| Base lead-time demand (sum of seven P50s) | 216.928928 |
| Sampled aggregate lead-time P50 | 216.559416 |
| Sampled aggregate lead-time P90 | 236.162624 |
| Safety stock | 24.924877 |
| Reorder point | 241.853806 |
| EOQ | 612.372436 |
| Recommended order | 624.000000 |
| Risk | high |
| Target service (fraction) | 0.950000 |
| Sampled stockout probability | 0.869200 |

- Inventory position = 160 + 40 − 0 = 200 units.
- Base lead-time demand sums 7 period P50 values = 216.929 units. This median-based proxy is not an asserted mathematical expectation.
- Reorder point = 216.929 + 24.9249 safety stock = 241.854 units.
- 200 <= 241.854; reorder_needed = True.
- When triggered, order the largest of target-position gap, available EOQ, MOQ and one order multiple; round up to the multiple, then apply any inventory-position cap.

## 1,000-path Monte Carlo simulation

Seed 42; 30 periods; lost-sales mode.

| Measure | Actual value |
|---|---:|
| fill_rate | 0.981067 |
| average_service_level | 0.965067 |
| cycle_service_level | 0.556500 |
| completed_cycles | 2000.000000 |
| average_inventory | 298.133651 |
| expected_lost_units | 17.617240 |
| expected_holding_cost | 78.359563 |
| expected_ordering_cost | 100.000000 |
| expected_stockout_cost | 140.937918 |
| expected_total_cost | 319.297481 |
| Total cost P10 | 180.803123 |
| Total cost P50 | 305.564979 |
| Total cost P90 | 466.316588 |

Costs are USD under the supplied demo inputs. These are estimated operating costs, not savings against an observed company policy. Cycle service can be much lower than fill rate: it counts whether a complete cycle has any shortage, and the initial stock/supply schedule can cause shortages despite a high nominal target.

Deterministic P50 simulation total cost: 312.709101.

## Policy comparison

Minimum simulated expected holding + ordering + shortage cost, subject to mean immediate fill rate >= minimum_fill_rate; MOQ, order multiples and inventory-position cap apply to every simulated order.

| Policy | Target | Fill rate | Expected cost | Feasible |
|---|---:|---:|---:|---|
| No safety stock | 95.000% | 97.934% | 327.818314 | True |
| Classical safety stock | 95.000% | 98.110% | 321.477629 | True |
| Forecast-quantile safety stock | 95.000% | 98.107% | 319.297481 | True |
| Optimized service-level policy | 90.000% | 98.099% | 318.878007 | True |

Recommended: **Optimized service-level policy**. Lowest cost among feasible evaluated policies.

## What-if and portfolio

What-if inputs: lead time 3, service target .99, on-hand 220, ordering cost 30. Same forecast/seed; scenario expected cost 128.002040. This changes multiple assumptions and is not a causal estimate of one lever's benefit.

Three independently trained series; portfolio inventory value 3360.00, recommended units 1200, expected operating cost 2147.007851. ABC distribution: `{'A': 2, 'B': 1}`. All three recommendation CSV rows were verified.

## Performance

Isolated SQLite in-process HTTP benchmark; 1,000 synthetic locations reuse one actual 30-period forecast, 1,000 uncertainty paths each. No model retraining. This is not a 1,000-model training benchmark.

Measured full batch HTTP time: **0.422220 s**; calculation/persistence service time: 0.358504 s.
Single recommendation: 0.022306 s; 1,000-path simulation: 0.006410 s.

Machine-local measurements, not latency guarantees. Benchmark snapshots are temporary; the walkthrough dataset/plans remain in PostgreSQL.

## Forecast metrics are separate

Untouched test accuracy: `{'mae': 4.85474394942122, 'rmse': 6.297065060502631, 'wape': 0.14448642706610773, 'smape': 0.1486867852696795, 'mase': 0.6875457752202764}`.
Probabilistic metrics: `{'pinball_p10': 1.1767841914893178, 'pinball_p50': 2.42737197471061, 'pinball_p90': 1.0280743150383747, 'coverage': 0.8, 'mean_interval_width': 15.73904553604525}`.

See [methodology](phase3-methodology.md) and [verification/limitations](phase3-verification.md).
