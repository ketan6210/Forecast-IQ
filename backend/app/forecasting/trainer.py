from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.app.evaluation.comparison import select_model
from backend.app.evaluation.metrics import calculate_metrics
from backend.app.evaluation.splitter import TimeSeriesSplitter
from backend.app.features.feature_engineering import FeatureEngineer
from backend.app.forecasting.base import ForecastModel
from backend.app.forecasting.linear_regression import LinearRegressionForecast
from backend.app.forecasting.moving_average import MovingAverage
from backend.app.forecasting.naive import NaiveForecast
from backend.app.forecasting.seasonal_naive import SeasonalNaive
from backend.app.schemas.forecast import ModelComparison
from backend.app.timing import timed

MODEL_REGISTRY: dict[str, type[ForecastModel]] = {
    model.name: model
    for model in (NaiveForecast, SeasonalNaive, MovingAverage, LinearRegressionForecast)
}


@dataclass
class TrainingResult:
    model: ForecastModel
    comparison: list[ModelComparison]
    split: dict
    selection_reason: str


def checked_predict(model: ForecastModel, horizon: int) -> np.ndarray:
    result = model.predict(horizon)
    if result.shape != (horizon,) or not np.isfinite(result).all() or (result < 0).any():
        raise ValueError(f"{model.name} returned invalid predictions.")
    return result


def train_baselines(series: pd.DataFrame, timings: dict[str, float]) -> TrainingResult:
    """Select on validation only; then refit to train+validation for final test evaluation.

    Feature precomputation is causal; each fit sees only its partition's prefix.
    All imputers/scalers are fitted anew on that prefix. Test results cannot influence selection.
    """
    series = series.sort_values("date").reset_index(drop=True)
    split = TimeSeriesSplitter().split(series)
    with timed("feature_generation_seconds", timings):
        features = FeatureEngineer().transform(series)
    with timed("training_seconds", timings):
        validation = {}
        for name, factory in MODEL_REGISTRY.items():
            model = factory().fit(split.train, features.iloc[: len(split.train)])
            predictions = checked_predict(model, len(split.validation))
            validation[name] = calculate_metrics(
                split.validation.units_sold.to_numpy(),
                predictions,
                split.train.units_sold.to_numpy(),
            )
        selected, reason = select_model(validation)
        before_test = pd.concat([split.train, split.validation], ignore_index=True)
        comparison = []
        for name, factory in MODEL_REGISTRY.items():
            model = factory().fit(before_test, features.iloc[: len(before_test)])
            predictions = checked_predict(model, len(split.test))
            test_metrics = calculate_metrics(
                split.test.units_sold.to_numpy(),
                predictions,
                before_test.units_sold.to_numpy(),
            )
            comparison.append(
                ModelComparison(
                    model=name,
                    validation_metrics=validation[name],
                    test_metrics=test_metrics,
                )
            )
        production = MODEL_REGISTRY[selected]().fit(series, features)
    return TrainingResult(production, comparison, split.boundaries(), reason)
