import numpy as np
import pandas as pd
import pytest

from backend.app.errors import AppError
from backend.app.evaluation.comparison import select_model
from backend.app.evaluation.metrics import calculate_metrics
from backend.app.evaluation.splitter import TimeSeriesSplitter
from backend.app.schemas.forecast import Metrics


def test_metrics_against_hand_calculation():
    result = calculate_metrics(np.array([10, 20, 0]), np.array([8, 24, 0]), np.arange(1, 15))
    assert result.mae == pytest.approx(2)
    assert result.rmse == pytest.approx(np.sqrt(20 / 3))
    assert result.wape == pytest.approx(0.2)
    assert result.smape == pytest.approx((4 / 18 + 8 / 44) / 3)
    assert result.mase == pytest.approx(2 / 7)


def test_zero_denominators_and_smape_zero_convention():
    result = calculate_metrics(np.zeros(7), np.zeros(7), np.zeros(28))
    assert result.wape is None
    assert result.mase is None
    assert result.smape == 0
    assert result.mae == result.rmse == 0


def test_all_zero_actual_with_nonzero_forecast():
    result = calculate_metrics(np.zeros(7), np.ones(7), np.arange(28))
    assert result.smape == 2
    assert result.wape is None


def test_mase_requires_sufficient_scaling_history():
    assert calculate_metrics(np.ones(7), np.zeros(7), np.arange(7)).mase is None


@pytest.mark.parametrize(
    "actual,predicted", [([], []), ([1, 2], [1]), ([np.nan], [1]), ([1], [np.inf])]
)
def test_invalid_metric_inputs(actual, predicted):
    with pytest.raises(ValueError):
        calculate_metrics(actual, predicted, np.arange(28))


def test_chronological_split_has_no_overlap(series):
    second = series.copy()
    second["store_id"] = "S2"
    split = TimeSeriesSplitter().split(pd.concat([series, second]).iloc[::-1])
    assert split.train.date.max() < split.validation.date.min()
    assert split.validation.date.max() < split.test.date.min()
    assert len(split.train) + len(split.validation) + len(split.test) == len(series) * 2
    assert len(set(split.train.date) & set(split.validation.date)) == 0
    assert split.train.date.is_monotonic_increasing


def test_split_rejects_insufficient_history(series):
    with pytest.raises(AppError, match="90"):
        TimeSeriesSplitter().split(series.iloc[:89])


def test_selection_uses_wape_then_mase():
    def metrics(wape, mase):
        return Metrics(mae=1, rmse=1, wape=wape, smape=1, mase=mase)

    selected, _ = select_model(
        {
            "naive": metrics(0.1, 2),
            "seasonal_naive": metrics(0.1, 1),
            "moving_average": metrics(0.2, 0.1),
        }
    )
    assert selected == "seasonal_naive"
    assert select_model({"naive": metrics(None, None)})[0] == "naive"
