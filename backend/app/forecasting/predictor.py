import logging
from datetime import timedelta
from uuid import uuid4

import numpy as np
import pandas as pd

from backend.app.data.frequency import resolve_frequency
from backend.app.data.preprocessing import prepare_daily_series
from backend.app.errors import AppError
from backend.app.forecasting.trainer import checked_predict, train_baselines
from backend.app.schemas.forecast import ForecastRequest, ForecastResponse
from backend.app.timing import timed

logger = logging.getLogger(__name__)


def forecast_series(frame: pd.DataFrame, request: ForecastRequest) -> ForecastResponse:
    if request.store_id not in set(frame.store_id):
        raise AppError(f"Unknown store: {request.store_id}.", 404)
    series = frame[(frame.store_id == request.store_id) & (frame.product_id == request.product_id)]
    if series.empty:
        raise AppError(f"Unknown product {request.product_id} for store {request.store_id}.", 404)
    declared = frame.attrs.get("frequency", "auto")
    if resolve_frequency(series.date, declared if declared != "mixed" else "auto") != "D":
        raise AppError(
            "Use Advanced forecasting for weekly or monthly data. "
            "This legacy baseline workflow uses daily data."
        )
    series = prepare_daily_series(series, request.missing_policy)
    missing = int(series.observation_missing.sum())
    if series.units_sold.isna().any():
        raise AppError(
            f"This series has {missing} missing sales observations. Supply observed sales, or "
            "explicitly select zero filling only if missing observations mean no sales.",
        )
    timings: dict[str, float] = {}
    try:
        trained = train_baselines(series, timings)
        with timed("forecast_generation_seconds", timings):
            predictions = checked_predict(trained.model, request.horizon)
    except AppError:
        raise
    except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
        logger.exception("Baseline model training or forecasting failed")
        raise AppError(
            "A baseline model could not be fitted. Check history and numeric data quality."
        ) from exc

    dates = pd.date_range(series.date.max() + timedelta(days=1), periods=request.horizon)
    selected = next(row for row in trained.comparison if row.model == trained.model.name)
    # Inventory must be observed on the last date; never silently substitute an older balance.
    inventory = series.iloc[-1].get("inventory", np.nan)
    inventory = float(inventory) if pd.notna(inventory) else None
    total = float(predictions.sum())
    warnings = (
        [f"Explicit zero policy applied to {missing} missing sales observations."]
        if missing
        else []
    )
    if "inventory" in series and inventory is None:
        warnings.append("Latest-date inventory is unknown; no inventory gap is calculated.")
    return ForecastResponse(
        run_id=str(uuid4()),
        dataset_id=request.dataset_id,
        store_id=request.store_id,
        product_id=request.product_id,
        horizon=request.horizon,
        missing_policy=request.missing_policy,
        model=trained.model.name,
        forecast=[
            {"date": date.date().isoformat(), "predicted_units": float(value)}
            for date, value in zip(dates, predictions, strict=True)
        ],
        history=[
            {"date": row.date.date().isoformat(), "actual": float(row.units_sold)}
            for row in series.itertuples()
        ],
        metrics=selected.test_metrics,
        validation_metrics=selected.validation_metrics,
        test_metrics=selected.test_metrics,
        comparison=trained.comparison,
        split=trained.split,
        summary={
            "historical_daily_average": float(series.units_sold.mean()),
            "last_7_day_average": float(series.units_sold.tail(7).mean()),
            "last_28_day_average": float(series.units_sold.tail(28).mean()),
            "forecast_daily_average": float(predictions.mean()),
            "forecast_total": total,
            "current_inventory": inventory,
            "inventory_gap": inventory - total if inventory is not None else None,
        },
        timings=timings,
        warnings=warnings,
        selection_reason=trained.selection_reason,
        assumptions=[
            "70/15/15 chronological split. Each holdout is forecast from a single origin.",
            "Model selected using validation WAPE, with validation MASE as the tie-breaker.",
            "Displayed evaluation metrics are from the untouched test partition.",
            "Future price stays at its latest known value; "
            "promotion, discount and holiday are zero.",
            "Selected external numeric predictors stay at their latest training-origin value; "
            "unknown history is imputed using training-only medians. Price is optional.",
            "Negative regression predictions are clipped to zero. "
            "No prediction intervals in Phase 1.",
        ],
    )
