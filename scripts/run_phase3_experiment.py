"""Measure inventory decisions from real saved forecasts using declared demo assumptions."""

import argparse
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import httpx
from fastapi.testclient import TestClient

from backend.app.db.models import AdvancedRun, Dataset
from backend.app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def post(client, path, body=None):
    response = client.post(path, json=body)
    response.raise_for_status()
    return response.json()


def benchmark(run: dict) -> dict:
    """1,000 explicitly synthetic inventory locations share one genuinely fitted forecast."""
    with TemporaryDirectory(prefix="forecastiq-inventory-benchmark-") as directory:
        temp = Path(directory)
        app = create_app(f"sqlite:///{temp / 'benchmark.db'}", temp / "storage")
        with TestClient(app) as client:
            with app.state.session_factory() as session:
                session.add(
                    Dataset(
                        id=run["dataset_id"],
                        filename="benchmark-reference.csv",
                        is_demo=True,
                        report={},
                        timings={},
                    )
                )
                session.flush()
                session.add(
                    AdvancedRun(
                        id=run["run_id"],
                        dataset_id=run["dataset_id"],
                        champion_model=run["champion_model"],
                        configuration={},
                        result=run,
                    )
                )
                session.commit()
            started = perf_counter()
            result = post(
                client,
                "/inventory/batch",
                {
                    "items": [
                        {
                            "forecast_run_id": run["run_id"],
                            "warehouse_id": f"BENCH_{i:04}",
                            "on_hand_inventory": 160,
                            "lead_time": 7,
                            "uncertainty_samples": 1000,
                        }
                        for i in range(1000)
                    ]
                },
            )
            elapsed = perf_counter() - started
            assert result["successful"] == 1000 and result["failed"] == 0
            return {
                "rows": 1000,
                "http_seconds": elapsed,
                "service_seconds": result["duration_seconds"],
                "description": "Isolated SQLite in-process HTTP benchmark; 1,000 synthetic "
                "locations reuse one actual 30-period forecast, 1,000 uncertainty paths each. "
                "No model retraining. This is not a 1,000-model training benchmark.",
            }


def experiment(client, base_url: str) -> dict:
    dataset = post(client, "/datasets/demo")
    trained = post(
        client,
        "/forecast/train",
        {
            "dataset_id": dataset["dataset_id"],
            "store_id": "STORE_01",
            "product_id": "SKU_001",
            "horizon": 30,
            "folds": 3,
        },
    )
    inputs = {
        "forecast_run_id": trained["run_id"],
        "on_hand_inventory": 160,
        "on_order_inventory": 40,
        "incoming_orders": [{"period": 3, "quantity": 40}],
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
        "seed": 42,
    }
    plan = post(client, "/inventory/optimize", inputs)
    config = {"plan_id": plan["plan_id"], "horizon": 30, "trials": 1000, "seed": 42}
    deterministic = post(client, "/inventory/simulate", {**config, "mode": "deterministic"})
    monte_carlo = post(client, "/inventory/simulate", config)
    comparison = post(client, "/inventory/policy-comparison", {**config, "minimum_fill_rate": 0.95})
    scenario = post(
        client,
        "/inventory/scenario",
        {
            **config,
            "changes": {
                "lead_time": 3,
                "service_level": 0.99,
                "on_hand_inventory": 220,
                "ordering_cost": 30,
            },
        },
    )
    # Independent series, each with its own trained output and inventory assumptions.
    other_runs = [
        post(
            client,
            "/forecast/train",
            {
                "dataset_id": dataset["dataset_id"],
                "store_id": "STORE_01",
                "product_id": sku,
                "horizon": 30,
                "folds": 2,
                "models": ["naive", "seasonal_naive", "moving_average"],
            },
        )
        for sku in ("SKU_002", "SKU_003")
    ]
    batch = post(
        client,
        "/inventory/batch",
        {
            "items": [
                {
                    **inputs,
                    "forecast_run_id": r["run_id"],
                    "on_hand_inventory": 120,
                    "annual_demand": annual,
                    "unit_cost": cost,
                }
                for r, annual, cost in zip(other_runs, (6000, 3000), (8, 4), strict=True)
            ]
        },
    )
    for item in batch["items"]:
        post(client, "/inventory/simulate", {**config, "plan_id": item["plan_id"]})
    params = {"dataset_id": dataset["dataset_id"]}
    summary = client.get("/inventory/kpis", params=params)
    summary.raise_for_status()
    abc = client.get("/inventory/abc-analysis", params=params)
    abc.raise_for_status()
    exported = client.get("/inventory/export", params=params)
    exported.raise_for_status()
    assert len(list(csv.DictReader(io.StringIO(exported.text)))) == 3
    assert abs(plan["inventory_position"] - 200) < 1e-9
    assert (
        abs(plan["reorder_point"] - plan["expected_lead_time_demand"] - plan["safety_stock"]) < 1e-9
    )
    assert plan["recommended_order_quantity"] % 12 == 0
    assert abs(plan["eoq"] - (2 * 12000 * 50 / 3.2) ** 0.5) < 1e-9
    assert (
        abs(
            monte_carlo["expected_total_cost"]
            - sum(
                monte_carlo[k]
                for k in (
                    "expected_holding_cost",
                    "expected_ordering_cost",
                    "expected_stockout_cost",
                )
            )
        )
        < 1e-8
    )
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "api": base_url,
        "data_note": "Actual fitted forecasts on bundled synthetic retail history. Inventory "
        "quantities, costs and service targets below are explicitly chosen demonstration "
        "assumptions; they are not observed company business data.",
        "dataset_id": dataset["dataset_id"],
        "forecast_run_id": trained["run_id"],
        "champion_model": trained["champion_model"],
        "test_metrics": trained["test_metrics"],
        "probabilistic_metrics": trained["probabilistic_metrics"],
        "forecast": trained["forecast"],
        "declared_inventory_inputs": inputs,
        "recommendation": plan,
        "deterministic_simulation": deterministic,
        "monte_carlo_simulation": monte_carlo,
        "policy_comparison": comparison,
        "scenario": scenario,
        "portfolio": summary.json(),
        "segmentation": abc.json(),
        "benchmark": benchmark(trained),
        "csv_export_rows_verified": 3,
    }


def write_report(result: dict):
    plan = result["recommendation"]
    sim = result["monte_carlo_simulation"]
    comp = result["policy_comparison"]
    link = (
        f"http://localhost:5180/?dataset={result['dataset_id']}"
        f"&view=inventory&plan={plan['plan_id']}"
    )
    lines = [
        "# Phase 3 measured walkthrough",
        "",
        f"Measured: {result['measured_at']}",
        "",
        result["data_note"],
        "",
        f"[Open this saved example in the running app]({link}).",
        "",
        f"Champion: **{result['champion_model']}**. Store STORE_01 / SKU_001; "
        "30 daily forecast periods. [Full numeric results](phase3-measured-results.json).",
        "",
        "## Declared demonstration inputs",
        "",
        "```json",
        json.dumps(result["declared_inventory_inputs"], indent=2),
        "```",
        "",
        "## Calculated recommendation",
        "",
        "| Measure | Actual value |",
        "|---|---:|",
    ]
    for label, key in [
        ("30-period P50 scenario sum", "forecast_p50_total"),
        ("30-period marginal P90 scenario sum (not a joint P90)", "forecast_p90_scenario_total"),
        ("On-hand inventory", "on_hand_inventory"),
        ("Inventory position", "inventory_position"),
        ("Base lead-time demand (sum of seven P50s)", "expected_lead_time_demand"),
        ("Sampled aggregate lead-time P50", "p50_lead_time_demand"),
        ("Sampled aggregate lead-time P90", "p90_lead_time_demand"),
        ("Safety stock", "safety_stock"),
        ("Reorder point", "reorder_point"),
        ("EOQ", "eoq"),
        ("Recommended order", "recommended_order_quantity"),
        ("Risk", "risk_level"),
        ("Target service (fraction)", "service_level"),
        ("Sampled stockout probability", "estimated_stockout_probability"),
    ]:
        v = plan[key]
        lines.append(
            f"| {label} | {v:.6f} |" if isinstance(v, (int, float)) else f"| {label} | {v} |"
        )
    lines += [
        "",
        *[f"- {s}" for s in plan["calculation_details"]],
        "",
        "## 1,000-path Monte Carlo simulation",
        "",
        "Seed 42; 30 periods; lost-sales mode.",
        "",
        "| Measure | Actual value |",
        "|---|---:|",
    ]
    for key in [
        "fill_rate",
        "average_service_level",
        "cycle_service_level",
        "completed_cycles",
        "average_inventory",
        "expected_lost_units",
        "expected_holding_cost",
        "expected_ordering_cost",
        "expected_stockout_cost",
        "expected_total_cost",
    ]:
        lines.append(f"| {key} | {sim[key]:.6f} |")
    lines += [
        f"| Total cost P10 | {sim['cost_distribution']['p10']:.6f} |",
        f"| Total cost P50 | {sim['cost_distribution']['p50']:.6f} |",
        f"| Total cost P90 | {sim['cost_distribution']['p90']:.6f} |",
        "",
        "Costs are USD under the supplied demo inputs. These are estimated operating costs, "
        "not savings against an observed company policy. Cycle service can be much lower "
        "than fill rate: it counts whether a complete cycle has any shortage, and the "
        "initial stock/supply schedule can cause shortages despite a high nominal target.",
        "",
        f"Deterministic P50 simulation total cost: "
        f"{result['deterministic_simulation']['expected_total_cost']:.6f}.",
        "",
        "## Policy comparison",
        "",
        comp["objective"],
        "",
        "| Policy | Target | Fill rate | Expected cost | Feasible |",
        "|---|---:|---:|---:|---|",
    ]
    for row in comp["policies"]:
        lines.append(
            f"| {row['policy']} | {row['target_service_level']:.3%} | "
            f"{row['fill_rate']:.3%} | {row['expected_total_cost']:.6f} | {row['feasible']} |"
        )
    lines += [
        "",
        f"Recommended: **{comp['recommended_policy']}**. {comp['recommendation_reason']}",
        "",
        "## What-if and portfolio",
        "",
        "What-if inputs: lead time 3, service target .99, on-hand 220, ordering cost 30. "
        f"Same forecast/seed; scenario expected cost "
        f"{result['scenario']['scenario']['simulation']['expected_total_cost']:.6f}. "
        "This changes multiple assumptions and is not a causal estimate of one lever's benefit.",
        "",
        f"Three independently trained series; portfolio inventory value "
        f"{result['portfolio']['total_inventory_value']:.2f}, recommended units "
        f"{result['portfolio']['total_recommended_order_quantity']:.0f}, expected operating "
        f"cost {result['portfolio']['expected_total_cost']:.6f}. "
        f"ABC distribution: `{result['portfolio']['abc_distribution']}`. "
        "All three recommendation CSV rows were verified.",
        "",
        "## Performance",
        "",
        result["benchmark"]["description"],
        "",
        f"Measured full batch HTTP time: **{result['benchmark']['http_seconds']:.6f} s**; "
        f"calculation/persistence service time: {result['benchmark']['service_seconds']:.6f} s.",
        f"Single recommendation: {plan['duration_seconds']:.6f} s; "
        f"1,000-path simulation: {sim['duration_seconds']:.6f} s.",
        "",
        "Machine-local measurements, not latency guarantees. Benchmark snapshots are temporary; "
        "the walkthrough dataset/plans remain in PostgreSQL.",
        "",
        "## Forecast metrics are separate",
        "",
        f"Untouched test accuracy: `{result['test_metrics']}`.",
        f"Probabilistic metrics: `{result['probabilistic_metrics']}`.",
        "",
        "See [methodology](phase3-methodology.md) and "
        "[verification/limitations](phase3-verification.md).",
        "",
    ]
    (ROOT / "docs/phase3-measured-results.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=180) as client:
        result = experiment(client, args.base_url)
    path = ROOT / "docs/phase3-measured-results.json"
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    write_report(result)
    print(
        json.dumps(
            {
                "report": str(path),
                "dataset_id": result["dataset_id"],
                "plan_id": result["recommendation"]["plan_id"],
                "cost": result["monte_carlo_simulation"]["expected_total_cost"],
                "benchmark": result["benchmark"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
