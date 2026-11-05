import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import acf, pacf

from backend.app.data.frequency import seasonal_period


def diagnostics(frame: pd.DataFrame, frequency: str) -> dict:
    """Descriptive diagnostics, not significance claims or mandatory stationarity tests."""
    values = frame.units_sold.to_numpy(float)
    size = len(values)
    season = seasonal_period(frequency)
    slope = float(np.polyfit(np.arange(size), values, 1)[0]) if size > 1 else 0.0
    relative = slope * max(1, size - 1) / max(float(np.mean(np.abs(values))), 1.0)
    median = np.median(values)
    mad = np.median(np.abs(values - median))
    # Robust MAD heuristic; no outlier flags for degenerate zero-MAD histories.
    outliers = np.abs(values - median) > 3.5 * 1.4826 * mad if mad > 0 else np.zeros(size, bool)
    correlations: list[float] = []
    partial: list[float] = []
    if size >= 8 and np.std(values) > 1e-10:
        nlags = min(60, size // 2 - 1)
        correlations = acf(values, nlags=nlags, fft=True).tolist()
        partial = pacf(values, nlags=nlags, method="ywm").tolist()
    strength = correlations[season] if len(correlations) > season else None
    seasonal = size >= 3 * season and strength is not None and strength > 0.25
    return {
        "frequency": frequency,
        "periods": size,
        "seasonal_period": season,
        "trend": "upward" if relative > 0.1 else "downward" if relative < -0.1 else "flat",
        "trend_slope_per_period": slope,
        "relative_trend": relative,
        "seasonality_detected": seasonal,
        "seasonal_autocorrelation": strength,
        "acf": [
            {"lag": i, "value": float(v)} for i, v in enumerate(correlations) if np.isfinite(v)
        ],
        "pacf": [{"lag": i, "value": float(v)} for i, v in enumerate(partial) if np.isfinite(v)],
        "missing_periods": int(frame.observation_missing.sum())
        if "observation_missing" in frame
        else 0,
        "outlier_count": int(outliers.sum()),
        "outliers": [
            {"date": row.date.date().isoformat(), "value": float(row.units_sold)}
            for row in frame.loc[outliers].itertuples()
        ][:100],
        "notes": [
            "Trend is a descriptive linear slope; "
            "seasonality uses a training-history ACF heuristic.",
            "Outliers use 3.5 scaled median absolute deviations and are not removed.",
        ],
    }
