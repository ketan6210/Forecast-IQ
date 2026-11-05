"""Small, independently testable inventory formulas; all time units are periods."""

import math
from statistics import NormalDist

from backend.app.schemas.inventory import InventoryInputs


def periods_per_year(frequency: str) -> float:
    return 365.25 if frequency == "D" else 365.25 / 7 if frequency.startswith("W-") else 12.0


def coverage_unit(frequency: str) -> str:
    return "days" if frequency == "D" else "weeks" if frequency.startswith("W-") else "months"


def inventory_position(on_hand: float, on_order: float, backorders: float) -> float:
    return on_hand + on_order - backorders


def z_score(service_level: float) -> float:
    if not 0.5 <= service_level < 1:
        raise ValueError("Service level must be in [0.5, 1).")
    return NormalDist().inv_cdf(service_level)


def analytical_safety_stock(
    service_level: float,
    demand_std: float,
    lead_time: float,
    mean_demand: float = 0,
    lead_time_std: float = 0,
) -> float:
    if min(demand_std, lead_time, mean_demand, lead_time_std) < 0:
        raise ValueError("Demand and lead-time moments cannot be negative.")
    variance = lead_time * demand_std**2 + mean_demand**2 * lead_time_std**2
    return z_score(service_level) * math.sqrt(variance)


def annual_holding_cost(inputs: InventoryInputs) -> float | None:
    if inputs.holding_cost_per_unit_per_year is not None:
        return inputs.holding_cost_per_unit_per_year
    if inputs.annual_holding_rate is not None and inputs.unit_cost is not None:
        return inputs.unit_cost * inputs.annual_holding_rate
    return None


def eoq(annual_demand: float | None, ordering: float | None, holding: float | None) -> dict:
    if annual_demand is None or ordering is None or holding is None:
        return {
            "value": None,
            "reason": "EOQ requires annual demand, ordering cost and annual holding cost.",
        }
    if min(annual_demand, ordering, holding) < 0:
        raise ValueError("EOQ inputs cannot be negative.")
    if holding == 0:
        return {"value": None, "reason": "EOQ has no finite optimum with zero annual holding cost."}
    return {"value": math.sqrt(2 * annual_demand * ordering / holding), "reason": None}


def order_quantity(
    position: float,
    reorder_point: float,
    target: float,
    economic_quantity: float | None,
    inputs: InventoryInputs,
) -> tuple[float, str | None]:
    if position > reorder_point:
        return 0.0, None
    if max(target - position, economic_quantity or 0, inputs.minimum_order_quantity) <= 0:
        return 0.0, "No positive replenishment requirement."
    raw = max(
        target - position,
        economic_quantity or 0,
        inputs.minimum_order_quantity,
        inputs.order_multiple,
    )
    quantity = math.ceil(raw / inputs.order_multiple - 1e-10) * inputs.order_multiple
    if inputs.max_inventory_position is not None:
        capacity = max(0, inputs.max_inventory_position - position)
        cap = math.floor(capacity / inputs.order_multiple + 1e-10) * inputs.order_multiple
        if quantity > cap:
            if cap < max(inputs.minimum_order_quantity, inputs.order_multiple):
                return 0.0, "Inventory-position cap prevents a feasible MOQ/order-multiple order."
            return cap, "Order limited by the configured inventory-position cap."
    return quantity, None
