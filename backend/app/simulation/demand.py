"""Explicit predictive path approximations, not sums of marginal quantiles."""

import numpy as np

from backend.app.errors import AppError
from backend.app.schemas.inventory import InventoryInputs


def demand_paths(
    forecast: dict, inputs: InventoryInputs, count: int, horizon: int, seed: int
) -> tuple[np.ndarray, dict]:
    points = forecast["forecast"]
    if not 1 <= horizon <= len(points):
        raise AppError(
            "Saved forecast does not cover this horizon. Train a longer Phase 2 forecast."
        )
    q = np.array([[p["p10"], p["p50"], p["p90"]] for p in points[:horizon]], float)
    if not np.isfinite(q).all() or (q < 0).any() or (np.diff(q, axis=1) < 0).any():
        raise AppError("Saved forecast has invalid demand quantiles.")
    rng = np.random.default_rng(seed)
    if inputs.sampling_method == "residual_bootstrap":
        records = forecast.get("calibration", {}).get("records", [])
        residuals = np.asarray([r["residual"] for r in records], float)
        if len(residuals) < 20 or not np.isfinite(residuals).all():
            raise AppError(
                "Residual bootstrap needs 20 saved calibration errors. "
                "Choose the explicit quantile approximation or retrain the forecast."
            )
        block = min(inputs.block_size, len(residuals))
        starts = rng.integers(0, len(residuals), (count, int(np.ceil(horizon / block))))
        index = ((starts[:, :, None] + np.arange(block)) % len(residuals)).reshape(count, -1)
        errors = residuals[index[:, :horizon]] - np.median(residuals)
        values = np.maximum(0, q[:, 1] + errors)
        detail = {
            "method": "Circular block bootstrap of centered, held-out forecast errors",
            "block_size": block,
            "residual_count": len(residuals),
            "assumptions": "Errors remain representative of future demand. Blocks preserve local "
            "dependence only; block_size=1 assumes independent errors. Refits and pooled forecast "
            "leads limit calibration. Empirical tails cannot represent unseen extremes.",
        }
    else:
        values = np.empty((count, horizon))
        uniforms = rng.random((count, horizon))
        for period, (low, median, high) in enumerate(q):
            # Linear quantile interpolation with explicitly extrapolated, bounded tails.
            endpoints = [
                max(0, low - (median - low) / 4),
                low,
                median,
                high,
                high + (high - median) / 4,
            ]
            values[:, period] = np.interp(uniforms[:, period], [0, 0.1, 0.5, 0.9, 1], endpoints)
        detail = {
            "method": "Piecewise-linear inverse CDF through P10/P50/P90; independent periods",
            "assumptions": "Tail endpoints extrapolate adjacent quantile slopes to q=0 and q=1, "
            "clipping demand at zero. Requested levels above 90% rely on this bounded-tail "
            "assumption, not native calibrated P95/P99 forecasts. "
            "Cross-period dependence is absent.",
        }
    return values, {**detail, "seed": seed, "paths": count, "horizon": horizon}


def lead_times(inputs: InventoryInputs, size, seed: int) -> np.ndarray:
    if inputs.lead_time_std == 0:
        return np.full(size, inputs.lead_time, dtype=int)
    # Positive Gamma moments; rounding gives arrivals in whole observation periods.
    shape = (inputs.lead_time / inputs.lead_time_std) ** 2
    scale = inputs.lead_time_std**2 / inputs.lead_time
    return np.rint(np.random.default_rng(seed).gamma(shape, scale, size)).astype(int)


def lead_time_distribution(forecast: dict, inputs: InventoryInputs) -> tuple[np.ndarray, dict]:
    horizon = len(forecast["forecast"])
    if inputs.lead_time > horizon:
        raise AppError("Lead time exceeds the saved forecast horizon. Train a longer forecast.")
    values, detail = demand_paths(
        forecast, inputs, inputs.uncertainty_samples, horizon, inputs.seed
    )
    lead = lead_times(inputs, len(values), inputs.seed + 1)
    if lead.max() > horizon:
        raise AppError(
            "Sampled variable lead times exceed available forecasts. Supply a longer "
            "forecast or review lead-time variability; tails are not silently truncated."
        )
    cumulative = np.column_stack([np.zeros(len(values)), np.cumsum(values, axis=1)])
    totals = cumulative[np.arange(len(values)), lead]
    return totals, {
        **detail,
        "sampled_mean_lead_time": float(lead.mean()),
        "sampled_lead_time_std": float(lead.std()),
        "lead_time_model": "Fixed"
        if inputs.lead_time_std == 0
        else "Nonnegative rounded Gamma with supplied pre-rounding mean/std",
    }
