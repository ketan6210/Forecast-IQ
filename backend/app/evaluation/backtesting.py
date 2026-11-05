from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.app.errors import AppError
from backend.app.schemas.advanced import TrainingRequest


@dataclass(frozen=True)
class Fold:
    number: int
    train_start: int
    train_end: int
    validation_end: int


@dataclass
class BacktestPlan:
    folds: list[Fold]
    calibration_start: int
    test_start: int
    horizon: int


def make_plan(size: int, request: TrainingRequest) -> BacktestPlan:
    """Reserve disjoint calibration and final test blocks before constructing folds."""
    calibration_size = max(20, request.horizon * 2)
    test_start = size - request.horizon
    calibration_start = test_start - calibration_size
    first_origin = calibration_start - request.folds * request.horizon
    if first_origin < 60:
        needed = 60 + (request.folds + 1) * request.horizon + calibration_size
        raise AppError(
            f"This configuration needs at least {needed} periods; found {size}. "
            "Reduce the horizon/folds or supply more history."
        )
    folds = []
    for i in range(request.folds):
        origin = first_origin + i * request.horizon
        start = max(0, origin - request.window_size) if request.window == "rolling" else 0
        folds.append(Fold(i + 1, start, origin, origin + request.horizon))
    return BacktestPlan(folds, calibration_start, test_start, request.horizon)


def metric_summary(folds: list[dict]) -> dict:
    result = {}
    for key in ("mae", "rmse", "wape", "smape", "mase"):
        available = [(f["fold"], f["metrics"][key]) for f in folds if f["metrics"][key] is not None]
        values = np.array([value for _, value in available])
        result[key] = {
            "mean": float(values.mean()) if len(values) else None,
            "median": float(np.median(values)) if len(values) else None,
            "std": float(values.std(ddof=1)) if len(values) > 1 else 0.0 if len(values) else None,
            "best_fold": min(available, key=lambda x: x[1])[0] if available else None,
            "worst_fold": max(available, key=lambda x: x[1])[0] if available else None,
            "defined_folds": len(values),
        }
    return result


def date_bounds(frame: pd.DataFrame) -> dict:
    return {
        "start": frame.date.iloc[0].date().isoformat(),
        "end": frame.date.iloc[-1].date().isoformat(),
        "periods": len(frame),
    }
