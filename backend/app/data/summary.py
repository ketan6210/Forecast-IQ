"""Descriptive EDA over observed period totals, preserving calendar gaps."""

import numpy as np
import pandas as pd

from backend.app.data.diagnostics import diagnostics


def summarize_demand(periods: pd.Series, frequency: str) -> dict:
    observed = periods.dropna()
    values = observed.to_numpy(float)
    missing = int(periods.isna().sum())
    if not len(values):
        return {
            "mean": None,
            "median": None,
            "standard_deviation": None,
            "cv": None,
            "minimum": None,
            "maximum": None,
            "trend": None,
            "trend_slope_per_period": None,
            "outlier_count": 0,
            "outliers": [],
            "seasonality_detected": None,
            "missing_periods": missing,
            "notes": ["No observed demand in this selection."],
        }
    mean, median = float(values.mean()), float(np.median(values))
    std = float(values.std(ddof=1)) if len(values) > 1 else None
    positions = np.flatnonzero(periods.notna().to_numpy())
    slope = float(np.polyfit(positions, values, 1)[0]) if len(values) > 1 else 0.0
    relative = slope * max(1, len(periods) - 1) / max(float(np.mean(np.abs(values))), 1)
    mad = np.median(np.abs(values - median))
    flagged = (
        np.abs(values - median) > 3.5 * 1.4826 * mad if mad > 0 else np.zeros(len(values), bool)
    )
    seasonal = None
    if not missing:
        info = diagnostics(pd.DataFrame({"date": observed.index, "units_sold": values}), frequency)
        seasonal = info["seasonality_detected"]
    return {
        "mean": mean,
        "median": median,
        "standard_deviation": std,
        "cv": std / mean if std is not None and mean > 0 else None,
        "minimum": float(values.min()),
        "maximum": float(values.max()),
        "trend": "upward" if relative > 0.1 else "downward" if relative < -0.1 else "flat",
        "trend_slope_per_period": slope,
        "seasonality_detected": seasonal,
        "outlier_count": int(flagged.sum()),
        "outliers": [
            {"date": day.date().isoformat(), "value": float(v)}
            for day, v in observed[flagged].items()
        ][:100],
        "missing_periods": missing,
        "notes": [
            "Statistics describe observed totals across the selected series per period. "
            "Partial observations can understate totals; missing values are not zero-filled.",
            "Volatility is sample standard deviation; CV requires positive mean. "
            "Trend is a descriptive slope over calendar-period positions.",
            "Outliers use 3.5 scaled median absolute deviations, not automatic removal. "
            "Zero MAD yields no flags. ACF seasonality is unavailable with calendar gaps.",
        ],
    }
