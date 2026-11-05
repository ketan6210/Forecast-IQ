"""Exposure before replenishment, accounting for when existing supply arrives."""

import numpy as np

from backend.app.schemas.inventory import InventoryInputs
from backend.app.simulation.demand import demand_paths, lead_times


def supply_exposure(forecast: dict, inputs: InventoryInputs) -> dict:
    horizon = len(forecast["forecast"])
    paths, _ = demand_paths(forecast, inputs, inputs.uncertainty_samples, horizon, inputs.seed)
    # Same draws as lead_time_distribution. Zero-lead orders are reviewed after demand,
    # so even immediate replenishment cannot undo a shortage in the first period.
    protection = np.maximum(1, lead_times(inputs, len(paths), inputs.seed + 1))
    receipts = np.zeros(horizon)
    for order in inputs.incoming_orders:
        if order.period <= horizon:
            receipts[order.period - 1] += order.quantity
    cumulative = np.cumsum(paths, axis=1) + inputs.backorders - np.cumsum(receipts)
    active = np.arange(horizon)[None, :] < protection[:, None]
    requirement = np.maximum(0, np.max(np.where(active, cumulative, 0), axis=1))
    shortfall = np.maximum(0, requirement - inputs.on_hand_inventory)
    probability = float(np.mean(shortfall > 1e-9))
    p50, p90, service = np.quantile(shortfall, [0.5, 0.9, inputs.service_level]).tolist()
    unscheduled = inputs.on_order_inventory > 0 and not inputs.incoming_orders
    return {
        "risk_level": "low" if probability <= 0.1 else "medium" if probability <= 0.5 else "high",
        "estimated_stockout_probability": probability,
        "shortage": {"p50": p50, "p90": p90},
        "expedite_quantity": service,
        "expedite_needed": service > 1e-9,
        "supply_schedule_status": "missing" if unscheduled else "known",
        "supply_timing_note": (
            "On-order inventory has no arrival schedule and is excluded from risk calculations. "
            "Enter arrival periods to replace this conservative assessment."
            if unscheduled
            else "Risk uses scheduled receipts before each period's demand; later receipts "
            "cannot erase an earlier shortage."
        ),
        "shortage_definition": "Quantiles of the largest cumulative supply deficit during "
        "sampled lead time (at least one review period), including initial backorders. "
        "This is immediate stock needed to avoid shortages, not simulated lost sales.",
        "probability_label": "Fraction of sampled paths with a supply deficit before "
        "replenishment, using receipt timing; model-based, not guaranteed.",
    }
