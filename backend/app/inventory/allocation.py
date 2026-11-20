"""One purchasing decision across SKUs, with integer pack and shared resource constraints."""

import math

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from backend.app.errors import AppError
from backend.app.schemas.inventory import AllocationRequest, InventoryInputs


def allocate(plans: list[dict], request: AllocationRequest) -> dict:
    by_id = {plan["plan_id"]: plan for plan in plans}
    if set(by_id) != {item.plan_id for item in request.items} or len(by_id) != len(plans):
        raise AppError("Allocation requires exactly the selected saved plans.")
    ordered = [by_id[item.plan_id] for item in request.items]
    identities = {(p["store_id"], p["sku_id"], p["location_id"]) for p in ordered}
    if len(identities) != len(ordered):
        raise AppError("Select only one plan per store/SKU/location; do not duplicate demand.")
    if any(p["dataset_id"] != request.dataset_id for p in ordered):
        raise AppError("All allocation plans must belong to the selected dataset.")
    scopes = {
        (p["location_id"], p["frequency"], p["forecast_start"], p["forecast_horizon"])
        for p in ordered
    }
    if len(scopes) != 1:
        raise AppError(
            "Select plans at one location with matching forecast start, frequency and horizon."
        )
    inputs = [InventoryInputs.model_validate(p["inputs"]) for p in ordered]
    currencies = {p.currency.strip() if p.currency else "" for p in inputs}
    if len(currencies) != 1 or not all(currencies):
        raise AppError("All plans require the same explicit currency; no conversion is assumed.")
    if any(p.unit_cost is None for p in inputs):
        raise AppError("Supply unit_cost on every saved plan before allocating purchases.")

    size = len(ordered)
    multiple = np.array([p.order_multiple for p in inputs])
    requested = np.array([p["recommended_order_quantity"] for p in ordered], float)
    if not np.isfinite(requested).all() or (requested < 0).any():
        raise AppError("A saved recommendation is invalid. Recalculate its inventory plan.")
    upper = np.floor(requested / multiple + 1e-9)
    for i, (plan, config) in enumerate(zip(ordered, inputs, strict=True)):
        if config.max_inventory_position is not None:
            room = max(0, config.max_inventory_position - plan["inventory_position"])
            upper[i] = min(upper[i], math.floor(room / multiple[i] + 1e-9))
    minimum = np.array(
        [max(1, math.ceil(p.minimum_order_quantity / p.order_multiple - 1e-9)) for p in inputs]
    )
    upper = np.where(upper >= minimum, upper, 0)
    if (upper > 1e7).any() or not np.isfinite(upper).all():
        raise AppError("Allocation supports at most ten million order multiples per item.")
    costs = np.array([p.unit_cost for p in inputs], float)
    weights = np.array([p.priority_weight for p in request.items])
    capacity = np.array([p.capacity_per_unit or 0 for p in request.items])

    # n_i integer packs, y_i binary activation: MOQ*y_i <= n_i <= upper_i*y_i.
    matrix = lil_matrix((2 * size + 2, 2 * size))
    for i in range(size):
        matrix[2 * i, i], matrix[2 * i, size + i] = 1, -upper[i]
        matrix[2 * i + 1, i], matrix[2 * i + 1, size + i] = -1, minimum[i]
    limits = np.zeros(2 * size + 2)
    matrix[-2, :size] = costs * multiple
    matrix[-1, :size] = capacity * multiple
    limits[-2] = request.purchasing_budget if request.purchasing_budget is not None else np.inf
    limits[-1] = request.available_capacity if request.available_capacity is not None else np.inf
    matrix = matrix.tocsc()
    objective = np.where(upper > 0, weights * multiple, 0)
    if not np.isfinite(matrix.data).all() or not np.isfinite(objective).all():
        raise AppError("Allocation coefficients exceed the supported numeric range.")
    objective = objective / max(float(objective.max()), np.finfo(float).tiny)
    solution = milp(
        c=np.r_[-objective, np.zeros(size)],
        integrality=np.ones(2 * size),
        bounds=Bounds(np.zeros(2 * size), np.r_[upper, np.ones(size)]),
        constraints=LinearConstraint(matrix.tocsc(), -np.inf, limits),
        options={"time_limit": 10.0, "mip_rel_gap": 0.0},
    )
    if solution.status not in (0, 1) or solution.x is None:
        raise AppError(
            "Allocation solver could not produce a feasible decision. Review inputs.", 503
        )
    packs = np.rint(solution.x[:size])
    packs[packs == 0] = 0.0  # Normalize solver negative zero before JSON/CSV serialization.
    quantities = packs * multiple
    spend = float(quantities @ costs)
    used = float(quantities @ capacity)

    def exceeds(value, maximum):
        return maximum is not None and value > maximum + max(1e-7, abs(maximum) * 1e-9)

    if (
        not np.isfinite(solution.x).all()
        or not np.allclose(packs, solution.x[:size], rtol=0, atol=1e-5)
        or (packs < 0).any()
        or (packs > upper).any()
        or ((packs > 0) & (packs < minimum)).any()
        or exceeds(spend, request.purchasing_budget)
        or exceeds(used, request.available_capacity)
    ):
        raise AppError(
            "Allocation failed its independent feasibility check; no decision saved.", 503
        )
    items = []
    for i, plan in enumerate(ordered):
        deferred = max(0, float(requested[i] - quantities[i]))
        items.append(
            {
                "plan_id": plan["plan_id"],
                "forecast_run_id": plan["forecast_run_id"],
                "sku_id": plan["sku_id"],
                "store_id": plan["store_id"],
                "location_id": plan["location_id"],
                "requested_quantity": float(requested[i]),
                "allocated_quantity": float(quantities[i]),
                "deferred_quantity": deferred,
                "priority_weight": float(weights[i]),
                "unit_cost": float(costs[i]),
                "purchase_cost": float(quantities[i] * costs[i]),
                "capacity_per_unit": request.items[i].capacity_per_unit,
                "capacity_used": float(quantities[i] * capacity[i])
                if request.available_capacity is not None
                else None,
                "minimum_order_quantity": inputs[i].minimum_order_quantity,
                "order_multiple": float(multiple[i]),
                "inventory_position": plan["inventory_position"],
                "max_inventory_position": inputs[i].max_inventory_position,
                "expedite_quantity": plan.get("expedite_quantity"),
                "status": "fulfilled"
                if deferred < 1e-7
                else "deferred"
                if quantities[i] == 0
                else "partial",
            }
        )
    gap = getattr(solution, "mip_gap", None)
    return {
        "dataset_id": request.dataset_id,
        "location_id": ordered[0]["location_id"],
        "currency": next(iter(currencies)),
        "items": items,
        "solver_status": "optimal" if solution.status == 0 else "feasible_time_limit",
        "relative_gap": float(gap) if gap is not None and np.isfinite(gap) else None,
        "objective": "Maximize sum(priority_weight × allocated units), capped at each saved "
        "recommendation, subject to shared purchasing budget, available capacity "
        "and pack/MOQ constraints.",
        "weighted_allocated_units": float(weights @ quantities),
        "total_requested_quantity": float(requested.sum()),
        "total_allocated_quantity": float(quantities.sum()),
        "total_deferred_quantity": float(sum(i["deferred_quantity"] for i in items)),
        "purchase_cost": spend,
        "purchasing_budget": request.purchasing_budget,
        "budget_remaining": max(0, request.purchasing_budget - spend)
        if request.purchasing_budget is not None
        else None,
        "available_capacity": request.available_capacity,
        "capacity_used": used if request.available_capacity is not None else None,
        "capacity_remaining": max(0, request.available_capacity - used)
        if request.available_capacity is not None
        else None,
        "capacity_unit": request.capacity_unit,
        "notes": [
            "One allocation for the selected saved plans at one location. This is not a purchase "
            "order and does not modify plans or their recurring simulation policies.",
            "Budget covers unit purchase costs only; ordering fees, taxes "
            "and freight are excluded.",
            "Available capacity is space reserved for these new orders after existing stock and "
            "committed receipts. Use one shared capacity unit; "
            "no demand-based space release assumed.",
            "Priority is per unit, defaults to one, and is supplied by the user. Weighted units "
            "are not profit, cost savings or a service-level guarantee. "
            "Equivalent optima may differ.",
            "Zero orders are allowed when MOQ or shared limits prevent replenishment. Expediting "
            "existing late supply remains a separate action.",
        ],
    }
