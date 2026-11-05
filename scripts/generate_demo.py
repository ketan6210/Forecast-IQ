"""Deterministically generate synthetic retail observations, not benchmark data."""

from pathlib import Path

import numpy as np
import pandas as pd


def generate_demo(destination: Path) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    products = [
        ("SKU_001", "Food", 36, 9.99),
        ("SKU_002", "Food", 24, 6.49),
        ("SKU_003", "Beverages", 52, 3.99),
        ("SKU_004", "Beverages", 40, 5.49),
        ("SKU_005", "Household", 18, 14.99),
        ("SKU_006", "Personal care", 15, 11.99),
    ]
    rows = []
    for store, factor, region in [("STORE_01", 1.0, "East"), ("STORE_02", 1.25, "West")]:
        for product, category, base, price in products:
            for i, day in enumerate(pd.date_range("2025-01-01", "2025-12-31")):
                promotion = int((i + int(product[-1]) * 3) % 35 < 4)
                discount = 0.15 if promotion else 0.0
                holiday = int((day.month, day.day) in [(1, 1), (7, 4), (11, 27), (12, 25)])
                seasonal = 1 + 0.18 * np.sin(2 * np.pi * (i - 40) / 365)
                weekend = 1.22 if day.dayofweek >= 5 else 1.0
                demand = base * factor * seasonal * weekend * (1 + 0.35 * promotion + 0.2 * holiday)
                units = max(0, int(round(demand + rng.normal(0, base * 0.12))))
                rows.append(
                    {
                        "date": day.date().isoformat(),
                        "store_id": store,
                        "product_id": product,
                        "category": category,
                        "units_sold": units,
                        "price": round(price * (1 + 0.015 * np.sin(i / 45)) * (1 - discount), 2),
                        "promotion": promotion,
                        "discount": discount,
                        "inventory": max(0, int(base * 14 - units + rng.normal(0, 15))),
                        "holiday": holiday,
                        "region": region,
                    }
                )
    frame = pd.DataFrame(rows)
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(destination, index=False)
    return frame


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "data" / "demo" / "retail_sales.csv"
    print(f"Generated {len(generate_demo(output)):,} synthetic rows at {output}")
