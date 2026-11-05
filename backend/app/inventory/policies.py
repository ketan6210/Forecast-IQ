"""Finite policy comparison with a stated cost/mean-fill-rate objective."""

from backend.app.inventory.recommendations import recommend
from backend.app.schemas.inventory import InventoryInputs, PolicyRequest
from backend.app.simulation.demand import lead_time_distribution
from backend.app.simulation.inventory_simulator import run_simulation


def compare_policies(forecast: dict, inputs: InventoryInputs, request: PolicyRequest) -> dict:
    uncertainty = lead_time_distribution(forecast, inputs)

    def evaluate(name: str, method: str, level: float) -> dict:
        changed = InventoryInputs.model_validate(
            {**inputs.model_dump(), "safety_stock_method": method, "service_level": level}
        )
        policy = recommend(forecast, changed, uncertainty)
        simulation = run_simulation(forecast, changed, policy, request)
        metrics = {
            key: value
            for key, value in simulation.items()
            if key not in {"trajectory", "example_path"}
        }
        return {
            "policy": name,
            "safety_stock_method": method,
            "target_service_level": level,
            "safety_stock": policy["safety_stock"],
            "reorder_point": policy["reorder_point"],
            **metrics,
            "feasible": simulation["fill_rate"] >= request.minimum_fill_rate,
        }

    grid = [
        evaluate(f"Quantile {level:.1%}", "quantile", level) for level in request.service_levels
    ]
    eligible_grid = [r for r in grid if r["feasible"] and r["expected_total_cost"] is not None]
    optimized = (
        min(eligible_grid, key=lambda r: (r["expected_total_cost"], r["safety_stock"]))
        if eligible_grid
        else None
    )
    policies = [
        evaluate("No safety stock", "none", inputs.service_level),
        evaluate("Classical safety stock", "demand_lead_time", inputs.service_level),
        evaluate("Forecast-quantile safety stock", "quantile", inputs.service_level),
    ]
    if optimized:
        policies.append({**optimized, "policy": "Optimized service-level policy"})
    candidates = [
        row for row in policies if row["feasible"] and row["expected_total_cost"] is not None
    ]
    best = (
        min(candidates, key=lambda r: (r["expected_total_cost"], r["safety_stock"]))
        if candidates
        else None
    )
    return {
        "objective": "Minimum simulated expected holding + ordering + shortage cost, "
        "subject to mean immediate fill rate >= minimum_fill_rate; MOQ, order multiples "
        "and inventory-position cap apply to every simulated order.",
        "minimum_fill_rate": request.minimum_fill_rate,
        "recommended_policy": best["policy"] if best else None,
        "recommendation_reason": "Lowest cost among feasible evaluated policies."
        if best
        else (
            "No policy is both feasible and fully costed. "
            "Supply missing costs or review constraints."
        ),
        "optimized_service_level": optimized["target_service_level"] if optimized else None,
        "service_level_comparison": grid,
        "policies": policies,
        "seed": request.seed,
        "trials": request.trials,
        "notes": [
            "Candidates use identical demand paths and lead-time draws (common random numbers).",
            (
                "Safety-stock target service and the optimization constraint on "
                "fill rate are distinct."
            ),
            "Finite candidate search is not a proof of a global optimum. Estimates use the same "
            "simulation paths for selection and reporting and have Monte Carlo/model uncertainty.",
            (
                "Higher service targets are not automatically preferred; measured "
                "cost and feasibility decide."
            ),
        ],
    }
