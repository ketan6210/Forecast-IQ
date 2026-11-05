import hashlib
import logging
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from backend.app.config import settings
from backend.app.data.diagnostics import diagnostics
from backend.app.data.frequency import (
    future_dates,
    prepare_series,
    resolve_frequency,
    seasonal_period,
)
from backend.app.errors import AppError
from backend.app.evaluation.backtesting import date_bounds, make_plan, metric_summary
from backend.app.evaluation.metrics import calculate_metrics
from backend.app.evaluation.model_selection import rank_models
from backend.app.evaluation.probabilistic_metrics import ResidualCalibrator, probabilistic_metrics
from backend.app.explainability.shap_values import explain_tree
from backend.app.models.base import checked
from backend.app.models.registry import FAMILIES, create_model, parameter_grid
from backend.app.schemas.advanced import TrainingRequest
from backend.app.services.artifacts import save_artifact

logger = logging.getLogger("forecastiq.advanced")


def training_history(series: pd.DataFrame, end: int, request: TrainingRequest) -> pd.DataFrame:
    start = max(0, end - request.window_size) if request.window == "rolling" else 0
    return series.iloc[start:end].reset_index(drop=True)


def fit_model(name: str, params: dict, history: pd.DataFrame, frequency: str, horizon: int):
    model = create_model(name, frequency, seasonal_period(frequency), horizon, params, len(history))
    return model.fit(history)


def backtest_config(
    series: pd.DataFrame, plan, request: TrainingRequest, name: str, params: dict, frequency: str
) -> dict:
    started = perf_counter()
    folds, stabilities = [], []
    notes = []
    for fold in plan.folds:
        history = series.iloc[fold.train_start : fold.train_end].reset_index(drop=True)
        validation = series.iloc[fold.train_end : fold.validation_end]
        model = fit_model(name, params, history, frequency, request.horizon)
        predicted = checked(model, len(validation))
        metrics = calculate_metrics(
            validation.units_sold.to_numpy(),
            predicted,
            history.units_sold.to_numpy(),
            seasonal_period(frequency),
        )
        stability = (
            float(np.abs(np.diff(predicted)).mean() / max(history.units_sold.mean(), 1))
            if len(predicted) > 1
            else 0.0
        )
        stabilities.append(stability)
        notes += model.notes
        folds.append(
            {
                "fold": fold.number,
                "train": date_bounds(history),
                "validation": date_bounds(validation),
                "metrics": metrics.model_dump(),
                "predictions": [
                    {
                        "date": row.date.date().isoformat(),
                        "actual": float(row.units_sold),
                        "predicted": float(value),
                    }
                    for row, value in zip(validation.itertuples(), predicted, strict=True)
                ],
            }
        )
    duration = perf_counter() - started
    logger.info(
        "model=%s operation=backtest folds=%d duration_seconds=%.6f", name, len(folds), duration
    )
    return {
        "model": name,
        "family": FAMILIES[name],
        "status": "ok",
        "parameters": params,
        "folds": folds,
        "summary": metric_summary(folds),
        "duration_seconds": duration,
        "forecast_stability": float(np.mean(stabilities)),
        "notes": sorted(set(notes)),
        "rank": None,
    }


def select_candidates(
    series: pd.DataFrame, request: TrainingRequest, plan, frequency: str
) -> list[dict]:
    """Seeded randomized tree search on chronological selection folds, before calibration/test."""
    rows = []
    for name in request.models:
        trials, successful = [], []
        for params in parameter_grid(
            name, request.tune, request.neural_epochs, request.tuning_trials, request.tuning_seed
        ):
            start = perf_counter()
            try:
                row = backtest_config(series, plan, request, name, params, frequency)
                successful.append(row)
                trials.append(
                    {
                        "parameters": params,
                        "status": "ok",
                        "summary": row["summary"],
                        "duration_seconds": row["duration_seconds"],
                    }
                )
            except Exception as exc:
                logger.warning("model=%s operation=backtest status=failed reason=%s", name, exc)
                trials.append(
                    {
                        "parameters": params,
                        "status": "failed",
                        "reason": str(exc),
                        "duration_seconds": perf_counter() - start,
                    }
                )
        if successful:
            # All-zero validation can make WAPE undefined for non-naive candidates too.
            best = min(
                successful,
                key=lambda r: (
                    r["summary"]["wape"]["mean"]
                    if r["summary"]["wape"]["mean"] is not None
                    else float("inf"),
                    r["summary"]["wape"]["std"] or 0,
                    r["summary"]["smape"]["mean"] or 0,
                ),
            )
            best["trials"] = trials
            best["tuning_duration_seconds"] = sum(t["duration_seconds"] for t in trials)
            best["search_method"] = (
                "seeded_randomized_chronological"
                if request.tune and name in {"lightgbm", "xgboost"}
                else "single_configuration"
            )
            best["tuning_seed"] = request.tuning_seed
            rows.append(best)
        else:
            rows.append(
                {
                    "model": name,
                    "family": FAMILIES[name],
                    "status": "skipped" if name == "nbeats" else "failed",
                    "reason": trials[-1]["reason"],
                    "trials": trials,
                    "rank": None,
                }
            )
    return rows


def quantile_points(dates, values: np.ndarray) -> list[dict]:
    return [
        {
            "date": date.date().isoformat(),
            "p10": float(v[0]),
            "p50": float(v[1]),
            "p90": float(v[2]),
        }
        for date, v in zip(dates, values, strict=True)
    ]


def train_advanced(
    frame: pd.DataFrame, request: TrainingRequest, run_id: str, artifact_dir: Path
) -> dict:
    started = perf_counter()
    raw = frame[
        (frame.store_id == request.store_id) & (frame.product_id == request.product_id)
    ].copy()
    if raw.empty:
        raise AppError("Unknown store/product series.", 404)
    declared = frame.attrs.get("frequency", "auto")
    requested_frequency = (
        declared if request.frequency == "auto" and declared != "mixed" else request.frequency
    )
    frequency = resolve_frequency(raw.date, requested_frequency)
    series = prepare_series(raw, frequency, request.missing_policy)
    if len(series) > settings.max_training_periods:
        raise AppError(
            f"Advanced training supports up to {settings.max_training_periods} periods per series."
        )
    plan = make_plan(len(series), request)
    comparison = select_candidates(series, request, plan, frequency)
    ranked = rank_models(comparison)
    if not ranked:
        raise AppError(
            "No candidate completed every backtest fold. Inspect data and training configuration."
        )
    warnings = []
    calibration_records = []
    # Fallback uses the previously established validation ranking, never test scores.
    champion = None
    for candidate in ranked:
        try:
            name, params = candidate["model"], candidate["parameters"]
            calibration_records = []
            for origin in range(plan.calibration_start, plan.test_start, request.horizon):
                stop = min(origin + request.horizon, plan.test_start)
                history = training_history(series, origin, request)
                model = fit_model(name, params, history, frequency, request.horizon)
                predicted = checked(model, stop - origin)
                for row, value in zip(
                    series.iloc[origin:stop].itertuples(), predicted, strict=True
                ):
                    calibration_records.append(
                        {
                            "date": row.date.date().isoformat(),
                            "actual": float(row.units_sold),
                            "predicted": float(value),
                            "residual": float(row.units_sold - value),
                            "training_end": history.date.iloc[-1].date().isoformat(),
                        }
                    )
            calibrator = ResidualCalibrator().fit(
                np.array([r["residual"] for r in calibration_records])
            )
            test_history = training_history(series, plan.test_start, request)
            test_model = fit_model(name, params, test_history, frequency, request.horizon)
            test_points = checked(test_model, request.horizon)
            champion = candidate
            break
        except Exception as exc:
            warnings.append(
                f"{candidate['model']} could not complete calibration/final fitting: {exc}. "
                "Trying next validation-ranked model."
            )
    if champion is None:
        raise AppError(
            "All validation-ranked candidates failed final fitting. Review training diagnostics."
        )
    test = series.iloc[plan.test_start :]
    quantiles = calibrator.predict(test_points)
    test_metrics = calculate_metrics(
        test.units_sold.to_numpy(),
        quantiles[:, 1],
        test_history.units_sold.to_numpy(),
        seasonal_period(frequency),
    ).model_dump()
    uncertainty_metrics = probabilistic_metrics(test.units_sold.to_numpy(), quantiles)
    # Only after final evaluation may the test observations enter a production fit.
    production_started = perf_counter()
    try:
        production = fit_model(
            champion["model"],
            champion["parameters"],
            training_history(series, len(series), request),
            frequency,
            request.horizon,
        )
        points = checked(production, request.horizon)
    except Exception as exc:
        raise AppError(
            "The selected model failed its production refit. "
            "Try a different candidate configuration."
        ) from exc
    future = calibrator.predict(points)
    production_seconds = perf_counter() - production_started
    now = datetime.now(timezone.utc).isoformat()
    common_metadata = {
        "model_version": "2.0.0",
        "training_timestamp": now,
        "forecast_horizon": request.horizon,
        "frequency": frequency,
        "external_features": frame.attrs.get("external_features", []),
        "dataset_id": request.dataset_id,
        "store_id": request.store_id,
        "product_id": request.product_id,
        "training_date_range": date_bounds(training_history(series, len(series), request)),
        "dataset_sha256": hashlib.sha256(series.to_csv(index=False).encode()).hexdigest(),
        "seed": 42,
        "python": platform.python_version(),
        "packages": {
            pkg: version(pkg)
            for pkg in ("numpy", "pandas", "scikit-learn", "statsmodels", "lightgbm", "xgboost")
        },
    }
    artifacts, explanations = {}, {}
    for row in comparison:
        if row["status"] != "ok":
            continue
        try:
            fit_started = perf_counter()
            model = (
                production
                if row["model"] == champion["model"]
                else fit_model(
                    row["model"],
                    row["parameters"],
                    training_history(series, len(series), request),
                    frequency,
                    request.horizon,
                )
            )
            manifest = {
                **common_metadata,
                "model_name": row["model"],
                "features": model.features,
                "hyperparameters": row["parameters"],
                "fitted_parameters": model.fitted_params,
                "backtest_metrics": row["summary"],
                "tuning_duration_seconds": row["tuning_duration_seconds"],
                "search_method": row["search_method"],
                "tuning_seed": request.tuning_seed,
                "production_fit_seconds": (
                    production_seconds
                    if row["model"] == champion["model"]
                    else perf_counter() - fit_started
                ),
            }
            if row["model"] == "nbeats":
                manifest["packages"] = {**common_metadata["packages"], "torch": version("torch")}
            artifacts[row["model"]] = save_artifact(artifact_dir, row["model"], model, manifest)
            if row["model"] in {"lightgbm", "xgboost"}:
                try:
                    explanations[row["model"]] = explain_tree(model, request.horizon)
                except Exception as exc:
                    warnings.append(f"SHAP unavailable for {row['model']}: {exc}")
        except Exception as exc:
            if row["model"] == champion["model"]:
                raise AppError("Champion artifact could not be persisted.", 500) from exc
            warnings.append(f"Could not persist {row['model']}: {exc}")
    save_artifact(
        artifact_dir,
        "calibrator",
        calibrator,
        {
            **common_metadata,
            "model_name": "calibrator",
            "offsets": calibrator.offsets.tolist(),
            "residual_count": calibrator.residual_count,
        },
    )
    dates = future_dates(series.date.iloc[-1], request.horizon, frequency)
    elapsed = perf_counter() - started
    logger.info(
        "run_id=%s champion=%s operation=train duration_seconds=%.6f",
        run_id,
        champion["model"],
        elapsed,
    )
    return {
        "run_id": run_id,
        "dataset_id": request.dataset_id,
        "store_id": request.store_id,
        "product_id": request.product_id,
        "frequency": frequency,
        "forecast_horizon": request.horizon,
        "champion_model": champion["model"],
        "created_at": now,
        "configuration": request.model_dump(),
        "selection_reason": "Mean WAPE across every rolling selection fold; "
        "ties use WAPE variability, sMAPE, MASE and forecast stability."
        if champion["summary"]["wape"]["mean"] is not None
        else "All validation WAPE values are undefined; explicit naive fallback.",
        "comparison": comparison,
        "forecast": quantile_points(dates, future),
        "history": [
            {"date": row.date.date().isoformat(), "actual": float(row.units_sold)}
            for row in series.itertuples()
        ],
        "test_metrics": test_metrics,
        "probabilistic_metrics": uncertainty_metrics,
        "test_predictions": [
            {**point, "actual": float(actual)}
            for point, actual in zip(
                quantile_points(test.date, quantiles), test.units_sold, strict=True
            )
        ],
        "calibration": {
            "method": "Prequential signed-residual quantiles with finite-rank correction",
            "residual_count": calibrator.residual_count,
            "offsets": calibrator.offsets.tolist(),
            "nominal_coverage": 0.8,
            "records": calibration_records,
        },
        "partitions": {
            "selection": date_bounds(series.iloc[: plan.calibration_start]),
            "calibration": date_bounds(series.iloc[plan.calibration_start : plan.test_start]),
            "test": date_bounds(test),
        },
        "diagnostics": diagnostics(series.iloc[: plan.calibration_start], frequency),
        "explainability": explanations,
        "artifacts": artifacts,
        "training_duration_seconds": elapsed,
        "warnings": warnings,
        "assumptions": [
            "Independent series models are fitted on demand; no all-catalog heavyweight training.",
            "Price is held at its last observed value; future event flags are zero. "
            "Inventory is excluded from model features.",
            "Explicitly selected numeric predictors are held at their latest training-origin "
            "value at every forecast lead. No realized holdout covariates are read. "
            "Missing price remains unknown; imputers learn only from each training fold.",
            "Calibration observations and final test observations are excluded "
            "from parameter/model selection.",
            "Residuals are pooled across forecast leads. P10/P50/P90 are marginal "
            "empirical estimates, not joint path bounds.",
            "Temporal dependence and model refits mean nominal 80% coverage is not guaranteed. "
            "Assess the measured final-test coverage.",
            "The test period is scored once after selection; production models are then "
            "refitted using all history (or the selected rolling window).",
            "N-BEATS requires 512 periods in every training window "
            "and an installed optional PyTorch runtime.",
        ],
    }
