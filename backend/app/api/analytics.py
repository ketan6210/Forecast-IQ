from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.data.frequency import resolve_frequency
from backend.app.data.repository import load_dataset
from backend.app.data.summary import summarize_demand
from backend.app.db.session import get_session
from backend.app.errors import AppError

router = APIRouter(prefix="/analytics", tags=["analytics"])


def grouped_sales(frame: pd.DataFrame, key: str, top: int | None = None) -> list[dict]:
    values = frame.groupby(key).units_sold.sum(min_count=1).dropna()
    if top:
        values = values.nlargest(top)
    return [{"name": str(name), "units": float(units)} for name, units in values.items()]


@router.get("/{dataset_id}")
def analytics(
    dataset_id: str,
    request: Request,
    store: str | None = None,
    product: str | None = None,
    category: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    session: Session = Depends(get_session),
) -> dict:
    df = load_dataset(dataset_id, session, request.app.state.storage)
    if date_from and date_to and date_from > date_to:
        raise AppError("Start date must be before or equal to end date.")
    for key, value in (("store_id", store), ("product_id", product), ("category", category)):
        if value is not None:
            if key not in df:
                raise AppError(f"This dataset has no {key} column.")
            df = df[df[key] == value]
    # Resolve before date filtering: two weekly rows must not become daily observations.
    declared = df.attrs.get("frequency", "auto")
    frequencies = {
        resolve_frequency(group.date, declared if declared != "mixed" else "auto")
        for _, group in df.groupby(["store_id", "product_id"])
    }
    if len(frequencies) > 1:
        raise AppError(
            "Selected series use different observation frequencies. "
            "Filter to series with a shared frequency before aggregating demand."
        )
    frequency = next(iter(frequencies)) if frequencies else "D"
    if date_from:
        df = df[df.date >= pd.Timestamp(date_from)]
    if date_to:
        df = df[df.date <= pd.Timestamp(date_to)]
    if df.empty:
        raise AppError(
            "No observations match these filters. Try a different date range or selection.", 404
        )
    daily = df.groupby("date").units_sold.sum(min_count=1)
    observed = daily.dropna()
    # Explicit nulls keep chart gaps visible instead of inventing zero demand.
    daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max(), freq=frequency))
    revenue_values = df.units_sold * df.price
    revenue = revenue_values.sum(min_count=1)
    total_units = df.units_sold.sum(min_count=1)
    weekday = observed.groupby(observed.index.dayofweek).mean()
    monthly = observed.groupby(observed.index.month).mean()
    category_df = (
        df.assign(category=df.category.fillna("Uncategorized")) if "category" in df else df
    )
    return {
        "frequency": frequency,
        "demand_statistics": summarize_demand(daily, frequency),
        "total_units": float(total_units) if pd.notna(total_units) else None,
        "total_revenue": float(revenue) if pd.notna(revenue) else None,
        "revenue_is_partial": bool(revenue_values.isna().any()),
        "average_daily_units": float(observed.mean()) if not observed.empty else None,
        "product_count": int(df.product_id.nunique()),
        "store_count": int(df.store_id.nunique()),
        "observation_count": len(df),
        "missing_sales_count": int(df.units_sold.isna().sum()),
        "date_min": df.date.min().date().isoformat(),
        "date_max": df.date.max().date().isoformat(),
        "sales_over_time": [
            {"date": day.date().isoformat(), "units": float(value) if pd.notna(value) else None}
            for day, value in daily.items()
        ],
        "sales_by_store": grouped_sales(df, "store_id"),
        "sales_by_category": grouped_sales(category_df, "category") if "category" in df else [],
        "top_products": grouped_sales(df, "product_id", 10),
        "weekday_pattern": [
            {
                "name": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][int(i)],
                "units": float(value),
            }
            for i, value in weekday.items()
        ],
        "monthly_seasonality": [
            {"name": date(2000, int(i), 1).strftime("%b"), "units": float(value)}
            for i, value in monthly.items()
        ],
    }
