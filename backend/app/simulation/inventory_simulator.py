"""Periodic-review (s, Q/target) simulation, with receipts before demand."""

from time import perf_counter

import numpy as np

from backend.app.errors import AppError
from backend.app.inventory.formulas import annual_holding_cost, order_quantity, periods_per_year
from backend.app.schemas.inventory import InventoryInputs, SimulationRequest
from backend.app.simulation.demand import demand_paths, lead_times


def distribution(values: np.ndarray) -> dict:
    p10, p50, p90 = np.quantile(values, [0.1, 0.5, 0.9]).tolist()
    return {"mean": float(np.mean(values)), "p10": p10, "p50": p50, "p90": p90}


def simulate_paths(
    demand: np.ndarray,
    delays: np.ndarray,
    inputs: InventoryInputs,
    policy: dict,
    frequency: str,
    dates: list[str],
    shortage_mode: str,
) -> dict:
    if inputs.on_order_inventory > 0 and not inputs.incoming_orders:
        raise AppError("Simulation requires arrival periods for existing on-order inventory.")
    demand = np.asarray(demand, float)
    if demand.ndim != 2 or not np.isfinite(demand).all() or (demand < 0).any():
        raise AppError("Simulation needs finite nonnegative demand paths.")
    n, horizon = demand.shape
    if (
        delays.shape != demand.shape
        or not np.isfinite(delays).all()
        or (delays < 0).any()
        or (delays != np.floor(delays)).any()
    ):
        raise AppError("Each path/period requires a nonnegative integer lead time.")
    on_hand = np.full(n, inputs.on_hand_inventory, float)
    on_order = np.full(n, inputs.on_order_inventory, float)
    backlog = np.full(n, inputs.backorders, float)
    queue: dict[int, np.ndarray] = {}
    for order in inputs.incoming_orders:
        queue.setdefault(order.period - 1, np.zeros(n))[:] += order.quantity
    holding_rate = annual_holding_cost(inputs)
    holding_factor = (holding_rate or 0) / periods_per_year(frequency)
    holding = np.zeros(n)
    ordering = np.zeros(n)
    stockout_cost = np.zeros(n)
    shortage = np.zeros(n)
    filled = np.zeros(n)
    inventory_sum = np.zeros(n)
    stockout_periods = np.zeros(n)
    order_counts = np.zeros(n)
    completed_cycles = np.zeros(n)
    good_cycles = np.zeros(n)
    cycle_open = np.zeros(n, bool)
    cycle_failed = np.zeros(n, bool)
    trajectory, first_path = [], []
    for t in range(horizon):
        receipts = queue.pop(t, np.zeros(n))
        received = receipts > 0
        closed = received & cycle_open
        completed_cycles += closed
        good_cycles += closed & ~cycle_failed
        cycle_open |= received
        cycle_failed[received] = False
        on_order -= receipts
        on_hand += receipts
        old_filled = np.minimum(on_hand, backlog)
        on_hand -= old_filled
        backlog -= old_filled
        beginning = on_hand.copy()
        fulfilled = np.minimum(on_hand, demand[:, t])
        missed = demand[:, t] - fulfilled
        on_hand -= fulfilled
        filled += fulfilled
        shortage += missed
        stockout_periods += missed > 1e-9
        cycle_failed |= (missed > 1e-9) | (backlog > 1e-9)
        if shortage_mode == "backorders":
            backlog += missed
        position = on_hand + on_order - backlog
        orders = np.array(
            [
                order_quantity(
                    float(p),
                    policy["reorder_point"],
                    policy["target_inventory_position"],
                    policy["eoq"],
                    inputs,
                )[0]
                for p in position
            ]
        )
        on_order += orders
        order_counts += orders > 0
        ordering_step = (orders > 0) * (inputs.ordering_cost or 0)
        shortage_step = missed * (inputs.stockout_cost or 0)
        ordering += ordering_step
        stockout_cost += shortage_step
        instant = np.where(delays[:, t] == 0, orders, 0)
        for delay in np.unique(delays[:, t]):
            if delay == 0:
                continue
            arrivals = np.where(delays[:, t] == delay, orders, 0)
            if arrivals.any():
                queue.setdefault(t + int(delay), np.zeros(n))[:] += arrivals
        # Zero-lead orders arrive after this period's demand; lost sales cannot be undone.
        on_hand += instant
        on_order -= instant
        instant_filled = np.minimum(on_hand, backlog)
        on_hand -= instant_filled
        backlog -= instant_filled
        immediate_cycle = (instant > 0) & cycle_open
        completed_cycles += immediate_cycle
        good_cycles += immediate_cycle & ~cycle_failed
        cycle_open |= instant > 0
        cycle_failed[instant > 0] = False
        inventory_sum += on_hand
        holding_step = on_hand * holding_factor
        holding += holding_step
        position = on_hand + on_order - backlog
        trajectory.append(
            {
                "date": dates[t],
                "period": t + 1,
                "inventory": distribution(on_hand),
                "demand": distribution(demand[:, t]),
                "inventory_position_mean": float(position.mean()),
                "mean_replenishment_received": float((receipts + instant).mean()),
                "mean_order_quantity": float(orders.mean()),
                "reorder_point": policy["reorder_point"],
                "safety_stock": policy["safety_stock"],
            }
        )
        first_path.append(
            {
                "date": dates[t],
                "period": t + 1,
                "beginning_inventory": float(beginning[0]),
                "replenishment_received": float(receipts[0] + instant[0]),
                "demand": float(demand[0, t]),
                "fulfilled_demand": float(fulfilled[0]),
                "fulfilled_backorders": float(old_filled[0] + instant_filled[0]),
                "shortage_units": float(missed[0]),
                "lost_units": float(missed[0]) if shortage_mode == "lost_sales" else 0.0,
                "backorders": float(backlog[0]),
                "on_hand_inventory": float(on_hand[0]),
                "on_order_inventory": float(on_order[0]),
                "inventory_position": float(position[0]),
                "order_quantity": float(orders[0]),
                "order_arrival_period": int(t + delays[0, t] + 1) if orders[0] > 0 else None,
                "holding_cost": float(holding_step[0]) if holding_rate is not None else None,
                "ordering_cost": float(ordering_step[0])
                if inputs.ordering_cost is not None
                else None,
                "stockout_cost": float(shortage_step[0])
                if inputs.stockout_cost is not None
                else None,
            }
        )
    total_demand = demand.sum(axis=1)
    fill = np.divide(filled, total_demand, out=np.ones(n), where=total_demand > 0)
    averages = inventory_sum / horizon
    total = holding + ordering + stockout_cost
    missing = [
        name
        for name, value in (
            ("annual holding cost", holding_rate),
            ("ordering cost", inputs.ordering_cost),
            ("stockout cost", inputs.stockout_cost),
        )
        if value is None
    ]
    average_value = (
        float(averages.mean()) * inputs.unit_cost if inputs.unit_cost is not None else None
    )
    return {
        "horizon": horizon,
        "paths": n,
        "shortage_mode": shortage_mode,
        "average_inventory": float(averages.mean()),
        "fill_rate": float(fill.mean()),
        "fill_rate_distribution": distribution(fill),
        "average_service_level": float((1 - stockout_periods / horizon).mean()),
        "service_level_definition": "Fraction of periods without newly unfilled demand",
        "cycle_service_level": float(good_cycles.sum() / completed_cycles.sum())
        if completed_cycles.sum()
        else None,
        "completed_cycles": int(completed_cycles.sum()),
        "cycle_note": "Only complete receipt-to-receipt cycles; boundary cycles are excluded.",
        "stockout_frequency": float((stockout_periods / horizon).mean()),
        "probability_any_stockout": float((stockout_periods > 0).mean()),
        "expected_lost_units": float(shortage.mean()) if shortage_mode == "lost_sales" else 0.0,
        "expected_shortage_units": float(shortage.mean()),
        "expected_ending_backorders": float(backlog.mean()),
        "expected_ending_on_order": float(on_order.mean()),
        "expected_order_count": float(order_counts.mean()),
        "expected_holding_cost": float(holding.mean()) if holding_rate is not None else None,
        "expected_ordering_cost": float(ordering.mean())
        if inputs.ordering_cost is not None
        else None,
        "expected_stockout_cost": float(stockout_cost.mean())
        if inputs.stockout_cost is not None
        else None,
        "expected_total_cost": float(total.mean()) if not missing else None,
        "cost_distribution": distribution(total) if not missing else None,
        "cost_unavailable_reason": "Missing " + ", ".join(missing) if missing else None,
        "average_inventory_distribution": distribution(averages),
        "ending_inventory_distribution": distribution(on_hand),
        "inventory_turnover": inputs.cogs_for_horizon / average_value
        if inputs.cogs_for_horizon is not None and average_value and average_value > 0
        else None,
        "turnover_note": (
            "Horizon COGS / average on-hand inventory value; requires supplied COGS and unit cost."
        ),
        "trajectory": trajectory,
        "example_path": first_path,
        "assumptions": [
            (
                "Receive scheduled orders, clear old backorders, serve current "
                "demand, then review inventory position."
            ),
            (
                "Static reorder point and target from the saved forecast; review "
                "once per observation period."
            ),
            (
                "Orders beyond the horizon remain outstanding; no invented future "
                "demand or terminal costs."
            ),
            (
                "Holding uses end-of-period on-hand stock and annual cost divided "
                "by frequency periods/year."
            ),
            (
                "Ordering is charged once per placed order; shortage cost once "
                "per newly unfilled unit."
            ),
            "Purchasing costs and profit are excluded from total inventory operating cost.",
            (
                "A zero-demand path has fill rate 1 by convention; no completed "
                "cycles gives null cycle service."
            ),
        ],
    }


def run_simulation(
    forecast: dict, inputs: InventoryInputs, policy: dict, request: SimulationRequest
) -> dict:
    started = perf_counter()
    horizon = request.horizon or len(forecast["forecast"])
    if horizon > len(forecast["forecast"]):
        raise AppError("Simulation horizon exceeds the saved forecast. Train a longer forecast.")
    if request.mode == "deterministic":
        paths = np.array([[p["p50"] for p in forecast["forecast"][:horizon]]])
        delays = np.full(paths.shape, inputs.lead_time, int)
        detail = {"method": "Deterministic period P50 demand and fixed mean lead time", "paths": 1}
    else:
        paths, detail = demand_paths(forecast, inputs, request.trials, horizon, request.seed)
        delays = lead_times(inputs, paths.shape, request.seed + 1)
    result = simulate_paths(
        paths,
        delays,
        inputs,
        policy,
        forecast["frequency"],
        [p["date"] for p in forecast["forecast"][:horizon]],
        request.shortage_mode,
    )
    return {
        **result,
        "mode": request.mode,
        "sampling": detail,
        "seed": request.seed,
        "duration_seconds": perf_counter() - started,
    }
