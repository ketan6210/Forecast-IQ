import numpy as np

from backend.app.errors import AppError
from backend.app.inventory.formulas import (
    analytical_safety_stock,
    annual_holding_cost,
    coverage_unit,
    eoq,
    inventory_position,
    order_quantity,
    periods_per_year,
    z_score,
)
from backend.app.inventory.supply import supply_exposure
from backend.app.schemas.inventory import InventoryInputs
from backend.app.simulation.demand import lead_time_distribution


def recommend(
    forecast: dict, inputs: InventoryInputs, uncertainty: tuple[np.ndarray, dict] | None = None
) -> dict:
    p50 = np.array([p["p50"] for p in forecast["forecast"]], float)
    if not len(p50):
        raise AppError("Saved forecast is empty. Train a Phase 2 forecast first.")
    totals, sampling = (
        uncertainty if uncertainty is not None else lead_time_distribution(forecast, inputs)
    )
    coverage = inputs.target_coverage_periods or min(len(p50), inputs.lead_time + 1)
    if coverage > len(p50) or coverage < inputs.lead_time:
        raise AppError(
            "Target coverage must cover lead time and fit inside the saved forecast horizon."
        )
    base = float(p50[: inputs.lead_time].sum())
    mean = float(p50.mean())
    historical = np.asarray([r["actual"] for r in forecast.get("history", [])], float)
    sigma = inputs.demand_std
    sigma_source = "User supplied"
    if sigma is None:
        sigma = float(historical.std(ddof=1)) if len(historical) > 1 else None
        sigma_source = "Sample standard deviation of observed historical demand"
    requested_quantile = float(np.quantile(totals, inputs.service_level))
    if inputs.safety_stock_method == "none":
        safety = 0.0
    elif inputs.safety_stock_method == "quantile":
        safety = max(0, requested_quantile - base)
    else:
        if sigma is None:
            raise AppError("Analytical safety stock requires two historical periods or demand_std.")
        safety = analytical_safety_stock(
            inputs.service_level,
            sigma,
            inputs.lead_time,
            mean,
            inputs.lead_time_std if inputs.safety_stock_method == "demand_lead_time" else 0,
        )
    position = inventory_position(
        inputs.on_hand_inventory, inputs.on_order_inventory, inputs.backorders
    )
    reorder = base + safety
    annual = inputs.annual_demand
    if annual is None and inputs.annualize_forecast:
        annual = mean * periods_per_year(forecast["frequency"])
    holding = annual_holding_cost(inputs)
    economic = eoq(annual, inputs.ordering_cost, holding)
    target = float(p50[:coverage].sum()) + safety
    quantity, constraint = order_quantity(position, reorder, target, economic["value"], inputs)
    low, median, high = np.quantile(totals, [0.1, 0.5, 0.9]).tolist()
    exposure = supply_exposure(forecast, inputs)
    risk = exposure["risk_level"]
    shortages = exposure["shortage"]
    explanations = [
        f"Inventory position = {inputs.on_hand_inventory:g} + {inputs.on_order_inventory:g} "
        f"− {inputs.backorders:g} = {position:g} units.",
        f"Base lead-time demand sums {inputs.lead_time} period P50 values = {base:g} units. "
        "This median-based proxy is not an asserted mathematical expectation.",
        f"Reorder point = {base:g} + {safety:g} safety stock = {reorder:g} units.",
        f"{position:g} {'<=' if position <= reorder else '>'} {reorder:g}; "
        f"reorder_needed = {position <= reorder}.",
        "When triggered, order the largest of target-position gap, available EOQ, MOQ and one "
        "order multiple; round up to the multiple, then apply any inventory-position cap.",
        exposure["supply_timing_note"],
        f"Immediate supply shortfall at the selected service quantile = "
        f"{exposure['expedite_quantity']:g} units. Expedite or reschedule existing supply "
        "where possible; this is not an additional purchase-order quantity.",
    ]
    assumptions = [
        "On-order and backorders default to zero; MOQ defaults to no restriction and order "
        "multiple to one whole unit. Supplied values override these visible assumptions.",
        "Analytical formulas assume independent demand across periods and independence of "
        "demand and lead time; historical variability may include trend/seasonality.",
        "Lead-time quantiles come from aggregated sampled paths, never a sum of marginal P90s.",
        "Inventory position includes all on-order stock. Risk and shortage scenarios instead "
        "use cumulative demand and scheduled receipts over each sampled lead time, with a "
        "minimum one-period exposure because review follows demand. Unscheduled stock is "
        "excluded conservatively. Expediting is an action to review, not an assumed receipt.",
        "No profit margin, purchasing budget or cost value is invented. EOQ excludes shortages "
        "and assumes stationary annual demand and fixed order/holding costs.",
    ]
    if inputs.annualize_forecast:
        assumptions.append(
            "Annual demand extrapolates the saved forecast mean by explicit request; "
            "uses 365.25 days, 365.25/7 weeks or 12 months per year."
        )
    return {
        "forecast_run_id": forecast["run_id"],
        "dataset_id": forecast["dataset_id"],
        "sku_id": forecast["product_id"],
        "product_id": forecast["product_id"],
        "store_id": forecast["store_id"],
        "warehouse_id": inputs.warehouse_id,
        "location_id": inputs.warehouse_id or forecast["store_id"],
        "supplier_id": inputs.supplier_id,
        "frequency": forecast["frequency"],
        "forecast_horizon": len(p50),
        "forecast_start": forecast["forecast"][0]["date"],
        "forecast": forecast["forecast"],
        "forecast_p50_total": float(p50.sum()),
        "forecast_p90_scenario_total": float(sum(p["p90"] for p in forecast["forecast"])),
        "forecast_total_note": "Sums of marginal quantiles are scenarios, not aggregate quantiles.",
        "on_hand_inventory": inputs.on_hand_inventory,
        "on_order_inventory": inputs.on_order_inventory,
        "backorders": inputs.backorders,
        "inventory_position": position,
        "current_inventory_position": position,
        "expected_lead_time_demand": base,
        "p10_lead_time_demand": low,
        "p50_lead_time_demand": median,
        "p90_lead_time_demand": high,
        "service_level_lead_time_demand": requested_quantile,
        "service_level": inputs.service_level,
        "z_score": z_score(inputs.service_level),
        "demand_std": sigma,
        "demand_std_source": sigma_source,
        "safety_stock": safety,
        "safety_stock_method": inputs.safety_stock_method,
        "reorder_point": reorder,
        "reorder_needed": position <= reorder,
        "units_below_reorder_point": max(0, reorder - position),
        "eoq": economic["value"],
        "eoq_reason": economic["reason"],
        "annual_demand": annual,
        "annual_holding_cost_per_unit": holding,
        "unit_cost": inputs.unit_cost,
        "historical_mean": float(historical.mean()) if len(historical) else None,
        "historical_std": float(historical.std(ddof=1)) if len(historical) > 1 else None,
        "target_coverage_periods": coverage,
        "target_inventory_position": target,
        "recommended_order_quantity": quantity,
        "constraint_note": constraint,
        "coverage_value": inputs.on_hand_inventory / mean if mean > 0 else None,
        "coverage_unit": coverage_unit(forecast["frequency"]),
        "coverage_reason": None if mean > 0 else "Undefined because forecast mean demand is zero.",
        "risk_level": risk,
        "stockout_risk": risk,
        **exposure,
        "revenue_at_risk": {k: v * inputs.selling_price for k, v in shortages.items()}
        if inputs.selling_price is not None
        else None,
        "inventory_value": inputs.on_hand_inventory * inputs.unit_cost
        if inputs.unit_cost is not None
        else None,
        "currency": inputs.currency,
        "sampling": sampling,
        "calculation_details": explanations,
        "assumptions": assumptions,
        "priority_components": {
            "risk_level": risk,
            "immediate_supply_shortfall": exposure["expedite_quantity"],
            "inventory_deficit": max(0, reorder - position),
            "forecast_volume": float(p50.sum()),
        },
        "priority_rule": (
            "High risk first, then immediate supply shortfall, reorder-point deficit "
            "and forecast volume."
        ),
    }
