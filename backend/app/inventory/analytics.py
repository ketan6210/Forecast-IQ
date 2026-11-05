"""Transparent portfolio sums and ABC/XYZ segmentation."""

from collections import Counter

import numpy as np


def portfolio(rows: list[dict]) -> dict:
    currencies = {row.get("currency") for row in rows}

    def complete_sum(field: str, monetary: bool = False):
        values = [row.get(field) for row in rows]
        if (
            not values
            or any(value is None for value in values)
            or (monetary and len(currencies) > 1)
        ):
            return None
        return float(sum(values))

    return {
        "series_count": len(rows),
        "total_inventory_value": complete_sum("inventory_value", True),
        "high_risk_series": sum(row["risk_level"] == "high" for row in rows),
        "below_reorder_point": sum(row["reorder_needed"] for row in rows),
        "expedite_needed": sum(bool(row.get("expedite_needed")) for row in rows),
        "plans_requiring_recalculation": sum(row.get("expedite_needed") is None for row in rows),
        "total_recommended_order_quantity": complete_sum("recommended_order_quantity"),
        "average_target_service_level": float(np.mean([r["service_level"] for r in rows]))
        if rows
        else None,
        "currency": next(iter(currencies)) if len(currencies) == 1 else None,
        "notes": [
            "Counts refer to SKU/location pairs. Monetary totals require complete costs "
            "and one shared currency; no currency conversion is assumed.",
            "Target service level is a configuration, not measured achieved service.",
        ],
    }


def segment(
    rows: list[dict], a: float = 0.8, b: float = 0.95, x: float = 0.5, y: float = 1
) -> dict:
    records = []
    currencies = {r.get("currency") for r in rows}
    comparable = len(currencies) <= 1
    for row in rows:
        annual = row.get("annual_demand")
        cost = row.get("unit_cost")
        mean = row.get("historical_mean")
        std = row.get("historical_std")
        cv = std / mean if mean is not None and mean > 0 and std is not None else None
        value = annual * cost if comparable and annual is not None and cost is not None else None
        records.append(
            {
                "sku_id": row["sku_id"],
                "store_id": row["store_id"],
                "location_id": row["location_id"],
                "annual_consumption_value": value,
                "cv": cv,
                "xyz_class": None if cv is None else "X" if cv <= x else "Y" if cv <= y else "Z",
                "abc_class": None,
                "cumulative_share": None,
                "matrix": None,
            }
        )
    ranked = sorted(
        records,
        key=lambda r: (-(r["annual_consumption_value"] or 0), r["sku_id"], r["location_id"]),
    )
    total = sum(r["annual_consumption_value"] or 0 for r in ranked)
    cumulative = 0.0
    for row in ranked:
        value = row["annual_consumption_value"]
        if value is not None and total > 0:
            # The item crossing a threshold remains in the preceding bucket.
            prior_share = cumulative / total
            row["abc_class"] = (
                "C" if value == 0 else "A" if prior_share < a else "B" if prior_share < b else "C"
            )
            cumulative += value
            row["cumulative_share"] = cumulative / total
            if row["xyz_class"]:
                row["matrix"] = row["abc_class"] + row["xyz_class"]
    return {
        "items": ranked,
        "abc_distribution": dict(Counter(r["abc_class"] or "unclassified" for r in ranked)),
        "matrix_distribution": dict(Counter(r["matrix"] or "unclassified" for r in ranked)),
        "thresholds": {"a": a, "b": b, "x": x, "y": y},
        "total_known_consumption_value": total,
        "excluded_from_abc": sum(r["annual_consumption_value"] is None for r in ranked),
        "notes": [
            "ABC uses annual demand × supplied unit cost, sorted by value. Threshold-crossing "
            "items remain in their starting bucket; classification is among known values only.",
            "XYZ uses historical sample standard deviation / mean. X<=0.5 and Y<=1 "
            "are configurable descriptive defaults, not universal business rules.",
            "Zero mean or insufficient history is unclassified. Segments are context, "
            "not automatic business prescriptions.",
        ],
    }
