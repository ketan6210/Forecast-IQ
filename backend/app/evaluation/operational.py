"""Recompute empirical coverage from saved holdouts matched to observed sales history."""

import numpy as np
import pandas as pd

from backend.app.evaluation.probabilistic_metrics import probabilistic_metrics


def score_predictions(points: pd.DataFrame) -> dict:
    actual = points.actual.to_numpy(float)
    quantiles = points[["p10", "p50", "p90"]].to_numpy(float)
    if (actual < 0).any() or (quantiles < 0).any():
        raise ValueError("Observed sales and quantiles must be nonnegative.")
    scores = probabilistic_metrics(actual, quantiles)
    error = abs(actual - quantiles[:, 1])
    denominator = abs(actual) + abs(quantiles[:, 1])
    return {
        "observations": len(actual),
        "mae": float(error.mean()),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "wape": float(error.sum() / actual.sum()) if actual.sum() else None,
        "smape": float(
            np.divide(
                2 * error, denominator, out=np.zeros_like(error), where=denominator != 0
            ).mean()
        ),
        **scores,
        "below_p10": float((actual < quantiles[:, 0]).mean()),
        "above_p90": float((actual > quantiles[:, 2]).mean()),
    }


def evaluate_catalog(runs: list[dict], history: pd.DataFrame) -> dict:
    canonical = {"date", "store_id", "product_id", "units_sold"}
    if canonical.issubset(history):
        history = history[list(canonical)].rename(
            columns={
                "store_id": "store",
                "product_id": "item",
                "units_sold": "sales",
            }
        )
    required = {"date", "store", "item", "sales"}
    if not required.issubset(history):
        raise ValueError("History requires date/store/item/sales or normalized ForecastIQ columns.")
    history = history.copy()
    for name in ("store", "item"):
        history[name] = history[name].astype(str)
    history["date"] = pd.to_datetime(history.date, errors="raise").dt.strftime("%Y-%m-%d")
    history["sales"] = pd.to_numeric(history.sales, errors="raise")
    if not np.isfinite(history.sales).all() or (history.sales < 0).any():
        raise ValueError("History must contain finite nonnegative observations.")
    if history.duplicated(["store", "item", "date"]).any():
        raise ValueError("History contains duplicate series/date observations.")
    indexed = history.set_index(["store", "item", "date"]).sales
    frames, series, identities = [], [], set()
    for run in runs:
        identity = (str(run["store_id"]), str(run["product_id"]))
        if identity in identities:
            raise ValueError("Multiple runs for one series would double-count the holdout.")
        identities.add(identity)
        parts = run["partitions"]
        if (
            not parts["selection"]["end"]
            < parts["calibration"]["start"]
            <= parts["calibration"]["end"]
            < parts["test"]["start"]
        ):
            raise ValueError("Selection, calibration and test dates must be disjoint and ordered.")
        points = pd.DataFrame(run["test_predictions"])
        dates = pd.to_datetime(points.date, errors="raise")
        if dates.duplicated().any() or not dates.is_monotonic_increasing:
            raise ValueError("Holdout dates must be unique and chronological.")
        if (
            len(points) != parts["test"]["periods"]
            or len(points) != run["forecast_horizon"]
            or points.date.iloc[0] != parts["test"]["start"]
            or points.date.iloc[-1] != parts["test"]["end"]
        ):
            raise ValueError("Holdout predictions disagree with the recorded test partition.")
        for row in points.itertuples():
            if (identity[0], identity[1], row.date) not in indexed.index:
                raise ValueError("Holdout date is absent from observed history.")
            if indexed.loc[(*identity, row.date)] != row.actual:
                raise ValueError("Saved holdout actuals do not match observed history.")
        scores = score_predictions(points)
        series.append(
            {
                "store_id": identity[0],
                "sku_id": identity[1],
                "run_id": run["run_id"],
                "model": run["champion_model"],
                "frequency": run["frequency"],
                "test_start": points.date.iloc[0],
                "test_end": points.date.iloc[-1],
                **scores,
            }
        )
        points["lead"] = np.arange(1, len(points) + 1)
        points["frequency"] = run["frequency"]
        frames.append(points)
    if not frames:
        raise ValueError("No saved holdout predictions found.")
    all_points = pd.concat(frames, ignore_index=True)
    coverages = np.array([row["coverage"] for row in series])
    return {
        "scope": "Recomputed saved final holdouts against source history; no retraining. "
        "Observed sales are not certified uncensored demand or representative of a business.",
        "series_count": len(series),
        "aggregate": score_predictions(all_points),
        "nominal_interval_coverage": 0.8,
        "coverage_gap": float(score_predictions(all_points)["coverage"] - 0.8),
        "series_coverage": {
            "minimum": float(coverages.min()),
            "median": float(np.median(coverages)),
            "maximum": float(coverages.max()),
            "series_below_nominal": int((coverages < 0.8).sum()),
        },
        "by_lead": [
            {"frequency": frequency, "lead": int(lead), **score_predictions(group)}
            for (frequency, lead), group in all_points.groupby(["frequency", "lead"])
        ],
        "series": series,
        "operational_validation": {
            "status": "UNVERIFIED",
            "observed_fill_rate": None,
            "observed_cycle_service": None,
            "supplier_lead_time": None,
            "reason": "No observed inventory movements, immediate fulfillment, stockouts or "
            "supplier order/receipt records supplied. No service outcome inferred from forecasts.",
        },
        "notes": [
            "Coverage is observation-weighted; series distributions are reported separately.",
            "No independent-sample confidence interval is claimed for correlated series/leads.",
            "Do not tune on these test results and continue calling the same period untouched.",
            "Aggregate forecast metrics may combine different units/scales; "
            "inspect per-series results.",
        ],
    }
