import itertools
from types import SimpleNamespace

import numpy as np
import pytest

from backend.app.errors import AppError
from backend.app.inventory.allocation import allocate
from backend.app.schemas.inventory import AllocationRequest, InventoryInputs


def plan(name, quantity=12, cost=2, multiple=2, minimum=4, **changes):
    config = InventoryInputs(
        on_hand_inventory=0,
        lead_time=2,
        unit_cost=cost,
        currency="USD",
        order_multiple=multiple,
        minimum_order_quantity=minimum,
    )
    return {
        "plan_id": name,
        "dataset_id": "d",
        "store_id": "s",
        "sku_id": name,
        "location_id": "w",
        "forecast_run_id": "f",
        "frequency": "D",
        "forecast_start": "2026-01-01",
        "forecast_horizon": 7,
        "inventory_position": 0,
        "inputs": config.model_dump(),
        "recommended_order_quantity": quantity,
        **changes,
    }


def request(plans, **changes):
    return AllocationRequest(
        dataset_id="d",
        items=[{"plan_id": p["plan_id"], "capacity_per_unit": 1} for p in plans],
        **{"purchasing_budget": 24, "available_capacity": 10, "capacity_unit": "slots", **changes},
    )


def test_joint_optimum_matches_exhaustive_integer_search():
    plans = [plan("a", cost=3), plan("b", cost=1, multiple=3, minimum=6)]
    req = request(plans)
    req.items[0].priority_weight = 2
    req.items[1].capacity_per_unit = 2
    result = allocate(plans, req)
    feasible = [
        (a, b)
        for a, b in itertools.product([0, 4, 6, 8, 10, 12], [0, 6, 9, 12])
        if 3 * a + b <= 24 and a + 2 * b <= 10
    ]
    assert result["weighted_allocated_units"] == max(2 * a + b for a, b in feasible)
    assert result["solver_status"] == "optimal"
    assert result["purchase_cost"] <= 24
    assert result["capacity_used"] <= 10
    assert [r["allocated_quantity"] for r in result["items"]] == [8, 0]


@pytest.mark.parametrize("budget,capacity", [(0, 100), (100, 0), (1, 1)])
def test_tight_resources_do_not_violate_moq(budget, capacity):
    plans = [plan("a"), plan("b")]
    result = allocate(plans, request(plans, purchasing_budget=budget, available_capacity=capacity))
    assert result["total_allocated_quantity"] == 0
    assert result["total_deferred_quantity"] == 24
    assert not any(np.signbit(item["allocated_quantity"]) for item in result["items"])


def test_fractional_multiples_zero_demand_and_position_cap():
    plans = [plan("a", quantity=1.5, cost=2, multiple=0.25, minimum=0.5), plan("b", quantity=0)]
    plans[0]["inputs"]["max_inventory_position"] = 1.1
    result = allocate(plans, request(plans, purchasing_budget=100, available_capacity=100))
    assert result["items"][0]["allocated_quantity"] == 1
    assert result["items"][1]["allocated_quantity"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"location_id": "other"},
        {"forecast_start": "2026-02-01"},
        {"frequency": "MS"},
        {"forecast_horizon": 30},
        {"dataset_id": "other"},
        {"sku_id": "a"},
    ],
)
def test_incompatible_or_duplicate_series_rejected(change):
    plans = [plan("a"), plan("b", **change)]
    with pytest.raises(AppError):
        allocate(plans, request(plans))


@pytest.mark.parametrize(
    "key,value", [("currency", None), ("currency", "EUR"), ("unit_cost", None)]
)
def test_missing_or_mixed_business_cost_inputs_rejected(key, value):
    plans = [plan("a"), plan("b")]
    plans[1]["inputs"][key] = value
    with pytest.raises(AppError):
        allocate(plans, request(plans))


def test_limit_solution_is_not_claimed_optimal_and_infeasible_result_rejected(monkeypatch):
    plans = [plan("a")]
    monkeypatch.setattr(
        "backend.app.inventory.allocation.milp",
        lambda **kw: SimpleNamespace(status=1, x=np.array([2.0, 1.0]), mip_gap=0.25),
    )
    assert allocate(plans, request(plans))["solver_status"] == "feasible_time_limit"
    monkeypatch.setattr(
        "backend.app.inventory.allocation.milp",
        lambda **kw: SimpleNamespace(status=0, x=np.array([7.0, 1.0]), mip_gap=0),
    )
    with pytest.raises(AppError, match="feasibility"):
        allocate(plans, request(plans))


def test_budget_only_and_capacity_only():
    plans = [plan("a")]
    req = AllocationRequest(dataset_id="d", items=[{"plan_id": "a"}], purchasing_budget=8)
    assert allocate(plans, req)["total_allocated_quantity"] == 4
    req = request(plans, purchasing_budget=None, available_capacity=6)
    assert allocate(plans, req)["total_allocated_quantity"] == 6
