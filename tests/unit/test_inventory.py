import math

import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.errors import AppError
from backend.app.inventory.analytics import portfolio, segment
from backend.app.inventory.formulas import (
    analytical_safety_stock,
    annual_holding_cost,
    eoq,
    inventory_position,
    order_quantity,
    z_score,
)
from backend.app.inventory.policies import compare_policies
from backend.app.inventory.recommendations import recommend
from backend.app.schemas.inventory import InventoryInputs, PolicyRequest, SimulationRequest
from backend.app.simulation.demand import demand_paths, lead_time_distribution, lead_times
from backend.app.simulation.inventory_simulator import run_simulation, simulate_paths


def forecast(values=(10, 20, 30, 40), frequency="D"):
    return {
        "run_id": "r",
        "dataset_id": "d",
        "store_id": "s",
        "product_id": "p",
        "frequency": frequency,
        "forecast": [
            {"date": f"2026-01-{i + 1:02}", "p10": v, "p50": v, "p90": v}
            for i, v in enumerate(values)
        ],
        "history": [{"actual": 10}, {"actual": 20}, {"actual": 30}],
        "calibration": {"records": [{"residual": 0} for _ in range(30)]},
    }


def inputs(**changes):
    return InventoryInputs.model_validate({"on_hand_inventory": 25, "lead_time": 2, **changes})


def test_inventory_position_separate_from_physical_stock():
    assert inventory_position(20, 30, 60) == -10
    r = recommend(forecast(), inputs(on_hand_inventory=20, on_order_inventory=30, backorders=60))
    assert r["on_hand_inventory"] == 20
    assert r["inventory_position"] == -10
    assert r["shortage"] == {"p50": 70, "p90": 70}
    assert r["supply_schedule_status"] == "missing"


@pytest.mark.parametrize("arrival,shortfall", [(1, 0), (2, 10), (3, 20), (20, 20)])
def test_late_receipts_cannot_erase_earlier_shortages(arrival, shortfall):
    r = recommend(
        forecast((10,) * 7),
        inputs(
            on_hand_inventory=0,
            on_order_inventory=1000,
            incoming_orders=[{"period": arrival, "quantity": 1000}],
        ),
    )
    assert r["inventory_position"] == 1000
    assert r["recommended_order_quantity"] == 0  # Do not duplicate an existing purchase.
    assert r["shortage"] == {"p50": shortfall, "p90": shortfall}
    assert r["expedite_quantity"] == shortfall
    assert r["estimated_stockout_probability"] == (1 if shortfall else 0)
    assert r["risk_level"] == ("high" if shortfall else "low")


def test_scheduled_receipts_clear_backorders_before_new_demand():
    r = recommend(
        forecast(),
        inputs(
            on_hand_inventory=20,
            on_order_inventory=30,
            backorders=60,
            incoming_orders=[{"period": 1, "quantity": 30}],
        ),
    )
    assert r["inventory_position"] == -10
    assert r["shortage"] == {"p50": 40, "p90": 40}


def test_zero_lead_time_still_exposes_first_period_demand_before_review():
    r = recommend(forecast((10,) * 7), inputs(on_hand_inventory=0, lead_time=0))
    assert r["expedite_quantity"] == 10
    assert r["estimated_stockout_probability"] == 1


def test_variable_lead_time_exposure_matches_deterministic_demand_prefixes():
    config = inputs(
        on_hand_inventory=15,
        lead_time=2,
        lead_time_std=0.5,
        on_order_inventory=100,
        incoming_orders=[{"period": 3, "quantity": 100}],
    )
    r = recommend(forecast((10,) * 7), config)
    sampled = lead_times(config, config.uncertainty_samples, config.seed + 1)
    # First period is covered; only paths waiting at least two periods miss five units.
    assert r["estimated_stockout_probability"] == np.mean(sampled >= 2)
    assert r["expedite_quantity"] == 5


@pytest.mark.parametrize(
    "level,z", [(0.9, 1.28155), (0.95, 1.64485), (0.975, 1.95996), (0.99, 2.32635)]
)
def test_service_level_z(level, z):
    assert z_score(level) == pytest.approx(z, abs=1e-5)


@pytest.mark.parametrize("frequency,unit", [("D", "days"), ("W-MON", "weeks"), ("MS", "months")])
def test_frequency_lead_demand_coverage_risk_and_reorder(frequency, unit):
    r = recommend(forecast(frequency=frequency), inputs())
    assert r["expected_lead_time_demand"] == 30
    assert r["p50_lead_time_demand"] == r["p90_lead_time_demand"] == 30
    assert r["coverage_value"] == 1
    assert r["coverage_unit"] == unit
    assert r["safety_stock"] == 0
    assert r["reorder_point"] == 30
    assert r["reorder_needed"] is True
    assert r["units_below_reorder_point"] == 5
    assert r["recommended_order_quantity"] == 35
    assert r["risk_level"] == "high"
    assert r["estimated_stockout_probability"] == 1
    assert r["shortage"]["p50"] == 5


def test_safety_stock_formulas_and_methods():
    z = z_score(0.95)
    assert analytical_safety_stock(0.95, 3, 4) == pytest.approx(z * 6)
    assert analytical_safety_stock(0.95, 3, 4, 20, 2) == pytest.approx(z * math.sqrt(1636))
    assert recommend(forecast(), inputs(safety_stock_method="demand", demand_std=3))[
        "safety_stock"
    ] == pytest.approx(z * 3 * math.sqrt(2))
    assert recommend(forecast(), inputs(safety_stock_method="none"))["safety_stock"] == 0


def test_quantile_aggregation_and_service_mapping():
    f = forecast((100,) * 6)
    f["calibration"]["records"] = [{"residual": v} for v in range(-50, 51)]
    low = recommend(f, inputs(service_level=0.9))
    high = recommend(f, inputs(service_level=0.99))
    totals, _ = lead_time_distribution(f, inputs())
    assert low["safety_stock"] == pytest.approx(np.quantile(totals, 0.9) - 200)
    assert high["safety_stock"] > low["safety_stock"]
    assert low["p90_lead_time_demand"] < 280  # two independent draws, not 2 × marginal P90
    assert recommend(f, inputs(on_hand_inventory=220))["risk_level"] == "medium"
    assert recommend(f, inputs(on_hand_inventory=500))["risk_level"] == "low"


def test_eoq_cost_styles_and_no_invented_inputs():
    assert eoq(1000, 50, 2)["value"] == pytest.approx(math.sqrt(50000))
    assert eoq(None, 50, 2)["value"] is None
    assert "zero" in eoq(1000, 50, 0)["reason"]
    assert eoq(0, 50, 2)["value"] == 0
    assert annual_holding_cost(inputs(unit_cost=20, annual_holding_rate=0.2)) == 4
    assert recommend(forecast(), inputs())["eoq"] is None
    assert recommend(forecast(), inputs())["annual_demand"] is None
    assert (
        recommend(forecast(frequency="MS"), inputs(annualize_forecast=True))["annual_demand"] == 300
    )


def test_practical_orders_and_cap():
    i = inputs(minimum_order_quantity=25, order_multiple=12)
    assert order_quantity(10, 30, 40, 5, i)[0] == 36
    assert order_quantity(31, 30, 80, 100, i)[0] == 0
    assert order_quantity(10, 30, 40, 100, i)[0] == 108
    assert (
        order_quantity(10, 30, 80, 100, inputs(max_inventory_position=34, order_multiple=12))[0]
        == 24
    )
    assert (
        order_quantity(
            10,
            30,
            80,
            100,
            inputs(max_inventory_position=34, minimum_order_quantity=25, order_multiple=12),
        )[0]
        == 0
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"on_hand_inventory": -1},
        {"lead_time": -1},
        {"lead_time": 1.5},
        {"service_level": 1},
        {"service_level": -0.1},
        {"minimum_order_quantity": -1},
        {"order_multiple": 0},
        {"ordering_cost": -1},
        {"stockout_cost": float("inf")},
        {"lead_time": 0, "lead_time_std": 1},
        {"safety_stock_method": "demand", "lead_time_std": 1},
        {"annual_holding_rate": 0.2},
        {"unit_cost": 5, "annual_holding_rate": 0.2, "holding_cost_per_unit_per_year": 2},
        {"annual_demand": 200, "annualize_forecast": True},
        {"incoming_orders": [{"period": 2, "quantity": 10}], "on_order_inventory": 11},
    ],
)
def test_invalid_business_inputs(changes):
    with pytest.raises(ValidationError):
        inputs(**changes)


def test_zero_demand_zero_stock_zero_lead_and_one_period():
    i = inputs(on_hand_inventory=0, lead_time=0)
    r = recommend(forecast((0,)), i)
    assert r["coverage_value"] is None
    assert r["p90_lead_time_demand"] == r["recommended_order_quantity"] == 0
    s = run_simulation(forecast((0,)), i, r, SimulationRequest(plan_id="p"))
    assert s["fill_rate"] == 1
    assert s["expected_order_count"] == 0
    assert s["cycle_service_level"] is None
    assert s["expected_total_cost"] is None
    assert s["inventory_turnover"] is None


def test_missing_history_and_uncovered_lead_times():
    with pytest.raises(AppError, match="Lead time exceeds"):
        recommend(forecast(), inputs(lead_time=90))
    with pytest.raises(AppError, match="Sampled variable lead"):
        recommend(forecast(), inputs(lead_time_std=20))
    f = forecast()
    f["calibration"]["records"] = []
    with pytest.raises(AppError, match="20 saved"):
        recommend(f, inputs())
    f["history"] = [{"actual": 10}]
    with pytest.raises(AppError, match="two historical"):
        recommend(f, inputs(sampling_method="quantile_interpolation", safety_stock_method="demand"))
    assert recommend(f, inputs(sampling_method="quantile_interpolation"))["safety_stock"] == 0


def test_bootstrap_reproducible_nonnegative_and_blocks_preserve_dependence():
    f = forecast((10,) * 30)
    f["calibration"]["records"] = [{"residual": v} for v in [-20] * 50 + [20] * 50]
    independent, _ = demand_paths(f, inputs(), 1000, 30, 13)
    blocks, _ = demand_paths(f, inputs(block_size=10), 1000, 30, 13)
    same, _ = demand_paths(f, inputs(block_size=10), 1000, 30, 13)
    np.testing.assert_array_equal(blocks, same)
    assert blocks.min() == 0
    assert blocks.sum(axis=1).std() > independent.sum(axis=1).std() * 2


def test_quantile_interpolation_tails_are_explicit_and_ordered():
    f = forecast((10,))
    f["forecast"][0].update(p10=5, p90=20)
    values, details = demand_paths(f, inputs(sampling_method="quantile_interpolation"), 10000, 1, 3)
    assert values.min() >= 3.75 and values.max() <= 22.5
    assert np.quantile(values, 0.5) == pytest.approx(10, abs=0.3)
    assert "bounded-tail" in details["assumptions"]
    f["forecast"][0]["p90"] = 1
    with pytest.raises(AppError, match="invalid demand quantiles"):
        demand_paths(f, inputs(), 100, 1, 1)


def simulate(demand=(8, 8, 8), **kwargs):
    i = inputs(
        on_hand_inventory=10,
        lead_time=1,
        holding_cost_per_unit_per_year=365.25,
        ordering_cost=2,
        stockout_cost=3,
        **kwargs,
    )
    p = {"reorder_point": 5, "target_inventory_position": 15, "eoq": None, "safety_stock": 0}
    return simulate_paths(
        np.array([demand]),
        np.ones((1, len(demand)), int),
        i,
        p,
        "D",
        [str(t) for t in range(len(demand))],
        "lost_sales",
    )


def test_hand_checked_receipts_orders_and_cost_ledger():
    r = simulate()
    path = r["example_path"]
    # Day 1: 10-8=2, order13. Day2: 2+13-8=7. Day3: 7-8=0, lost1, order15.
    assert [p["on_hand_inventory"] for p in path] == [2, 7, 0]
    assert [p["order_quantity"] for p in path] == [13, 0, 15]
    assert [p["replenishment_received"] for p in path] == [0, 13, 0]
    assert r["expected_holding_cost"] == 9
    assert r["expected_ordering_cost"] == 4
    assert r["expected_stockout_cost"] == 3
    assert r["expected_total_cost"] == 16
    assert r["fill_rate"] == pytest.approx(23 / 24)
    assert r["stockout_frequency"] == pytest.approx(1 / 3)
    assert r["expected_ending_on_order"] == 15
    assert r["average_inventory"] == 3


@pytest.mark.parametrize("mode,backlog,lost", [("lost_sales", 0, 5), ("backorders", 0, 0)])
def test_zero_lead_arrives_after_demand(mode, backlog, lost):
    i = inputs(on_hand_inventory=0, lead_time=0, stockout_cost=2)
    p = {"reorder_point": 10, "target_inventory_position": 10, "eoq": None, "safety_stock": 0}
    r = simulate_paths(np.array([[5.0]]), np.zeros((1, 1), int), i, p, "D", ["date"], mode)
    assert r["fill_rate"] == 0
    assert r["expected_ending_backorders"] == backlog
    assert r["expected_lost_units"] == lost
    assert r["expected_stockout_cost"] == 10
    assert r["expected_ending_on_order"] == 0


def test_existing_on_order_requires_arrival_dates_and_clears_old_backlog_first():
    f = forecast((5, 5, 5))
    i = inputs(on_hand_inventory=0, on_order_inventory=20, backorders=5)
    p = recommend(f, i)
    with pytest.raises(AppError, match="arrival periods"):
        run_simulation(f, i, p, SimulationRequest(plan_id="p"))
    i = inputs(
        on_hand_inventory=0,
        on_order_inventory=20,
        backorders=5,
        incoming_orders=[{"period": 2, "quantity": 20}],
        max_inventory_position=0,
    )
    p = recommend(f, i)
    r = run_simulation(
        f, i, p, SimulationRequest(plan_id="p", mode="deterministic", shortage_mode="backorders")
    )
    assert r["example_path"][0]["backorders"] == 10
    assert r["example_path"][1]["on_hand_inventory"] == 5
    assert r["example_path"][1]["backorders"] == 0
    assert r["expected_shortage_units"] == 5


def test_gamma_lead_time_sampling_is_reproducible():
    i = inputs(lead_time=7, lead_time_std=2)
    draws = lead_times(i, 10000, 7)
    np.testing.assert_array_equal(draws, lead_times(i, 10000, 7))
    assert draws.min() >= 0
    assert draws.mean() == pytest.approx(7, abs=0.1)


def test_policy_cost_objective_and_missing_costs_no_recommendation():
    f = forecast((10,) * 20)
    i = inputs(
        on_hand_inventory=40,
        lead_time=2,
        ordering_cost=5,
        stockout_cost=10,
        holding_cost_per_unit_per_year=3,
    )
    req = PolicyRequest(plan_id="p", trials=100, minimum_fill_rate=0.8)
    r = compare_policies(f, i, req)
    feasible = [p for p in r["policies"] if p["feasible"]]
    assert len(r["policies"]) == 4
    winner = next(p for p in feasible if p["policy"] == r["recommended_policy"])
    assert winner["expected_total_cost"] == min(p["expected_total_cost"] for p in feasible)
    assert r["policies"][0]["cost_distribution"] == r["policies"][2]["cost_distribution"]
    assert compare_policies(f, inputs(), req)["recommended_policy"] is None
    impossible = compare_policies(f, inputs(max_inventory_position=0), req)
    assert impossible["recommended_policy"] is None


def test_abc_value_threshold_crossing_xyz_and_missing_values():
    rows = [
        {
            "sku_id": str(i),
            "store_id": "s",
            "location_id": "s",
            "annual_demand": value,
            "unit_cost": 1,
            "historical_mean": 10,
            "historical_std": std,
        }
        for i, (value, std) in enumerate([(70, 2), (15, 7), (10, 15), (5, 0), (None, None)])
    ]
    r = segment(rows)
    assert [p["abc_class"] for p in r["items"]] == ["A", "A", "B", "C", None]
    assert [p["xyz_class"] for p in r["items"]] == ["X", "Y", "Z", "X", None]
    assert r["total_known_consumption_value"] == 100
    assert r["excluded_from_abc"] == 1
    rows[0]["currency"] = "USD"
    assert all(p["abc_class"] is None for p in segment(rows)["items"])


def test_portfolio_does_not_treat_missing_cost_as_zero():
    a = recommend(forecast(), inputs(unit_cost=3, currency="USD"))
    b = recommend(forecast(), inputs())
    assert portfolio([a, b])["total_inventory_value"] is None
    assert portfolio([a, a])["total_inventory_value"] == 150


@pytest.mark.parametrize("horizon", [30, 60, 90])
def test_supported_simulation_horizons_and_quantity_conservation(horizon):
    f = forecast((10,) * horizon)
    i = inputs(on_hand_inventory=5, lead_time=3, order_multiple=6)
    p = recommend(f, i)
    r = run_simulation(
        f,
        i,
        p,
        SimulationRequest(
            plan_id="p", horizon=horizon, mode="deterministic", shortage_mode="backorders"
        ),
    )
    hand, backlog, on_order = 5, 0, 0
    for row in r["example_path"]:
        hand += (
            row["replenishment_received"] - row["fulfilled_backorders"] - row["fulfilled_demand"]
        )
        backlog += row["shortage_units"] - row["fulfilled_backorders"]
        on_order += row["order_quantity"] - row["replenishment_received"]
        assert row["on_hand_inventory"] == pytest.approx(hand)
        assert row["backorders"] == pytest.approx(backlog)
        assert row["on_order_inventory"] == pytest.approx(on_order)
        assert row["inventory_position"] == pytest.approx(hand + on_order - backlog)
        assert row["order_quantity"] % 6 == 0


@pytest.mark.parametrize("frequency,periods", [("D", 365.25), ("W-MON", 365.25 / 7), ("MS", 12)])
def test_frequency_correct_holding_cost(frequency, periods):
    f = forecast((0,), frequency)
    i = inputs(
        on_hand_inventory=10,
        lead_time=0,
        holding_cost_per_unit_per_year=12,
        ordering_cost=0,
        stockout_cost=0,
        unit_cost=2,
        cogs_for_horizon=100,
    )
    r = run_simulation(f, i, recommend(f, i), SimulationRequest(plan_id="p", mode="deterministic"))
    assert r["expected_holding_cost"] == pytest.approx(120 / periods)
    assert r["inventory_turnover"] == 5


def test_completed_cycle_service_excludes_boundaries():
    i = inputs(
        on_hand_inventory=0,
        lead_time=1,
        on_order_inventory=10,
        incoming_orders=[{"period": 1, "quantity": 10}],
    )
    p = {"reorder_point": 5, "target_inventory_position": 10, "safety_stock": 0, "eoq": None}
    r = simulate_paths(
        np.array([[4.0] * 5]),
        np.ones((1, 5), int),
        i,
        p,
        "D",
        [str(t) for t in range(5)],
        "lost_sales",
    )
    assert r["completed_cycles"] == 2
    assert r["cycle_service_level"] == 1
