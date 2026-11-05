import numpy as np
import pandas as pd
import pytest

from backend.app.data.summary import summarize_demand
from backend.app.data.validator import DataValidator
from backend.app.errors import AppError
from backend.app.features.feature_engineering import FeatureEngineer
from backend.app.models.registry import create_model, parameter_grid
from backend.app.services.artifacts import load_artifact, save_artifact


def test_price_is_optional_and_not_invented(series):
    frame, report = DataValidator().validate(series.drop(columns="price"))
    assert report.validation_status == "PASS_WITH_WARNINGS"
    assert frame.price.isna().all()
    assert report.missing_value_summary["price"] == len(series)


@pytest.mark.parametrize("name", ["units_sold", "inventory", "unknown", "sales_lag_1", "month"])
def test_selected_predictors_reject_reserved_or_missing_columns(series, name):
    if name not in {"units_sold", "unknown"}:
        series[name] = 2
    with pytest.raises(AppError, match="predictor columns"):
        DataValidator().validate(series, external_features=[name])


@pytest.mark.parametrize("value", ["not-numeric", float("inf")])
def test_selected_external_values_validated(series, value):
    series["temperature"] = 20.0
    series["temperature"] = series.temperature.astype(object)
    series.loc[2, "temperature"] = value
    _, report = DataValidator().validate(series, external_features=["temperature"])
    assert report.validation_status == "FAIL"
    assert any("temperature contains" in e for e in report.errors)


def test_completed_baseline_lag_and_std_features(series):
    x = FeatureEngineer().transform(series)
    for lag in (1, 2, 3, 7, 14, 28):
        assert x.loc[50, f"sales_lag_{lag}"] == series.units_sold.iloc[50 - lag]
    for n in (7, 14, 28):
        assert x.loc[50, f"rolling_std_{n}"] == pytest.approx(
            series.units_sold.iloc[50 - n : 50].std()
        )
    assert len(FeatureEngineer().columns(x)) == len(set(FeatureEngineer().columns(x)))


@pytest.mark.parametrize("model", ["linear_regression", "lightgbm", "xgboost"])
def test_custom_covariates_use_training_origin_only_and_survive_serialization(
    series, model, tmp_path
):
    series["temperature"] = np.arange(len(series), dtype=float)
    series.loc[:3, "temperature"] = np.nan
    frame, _ = DataValidator().validate(series, external_features=["temperature"])
    history = frame.iloc[:100]
    fitted = create_model(model, "D", 7, 7, parameter_grid(model, False, 1)[0], 100).fit(history)
    assert "temperature" in fitted.features
    forecast = fitted.predict(7)
    column = fitted.features.index("temperature")
    assert (fitted.forecast_features[:, column] == 99).all()
    assert fitted.imputer.statistics_[column] == pytest.approx(np.median(np.arange(28, 100)))
    frame.loc[100:, ["temperature", "units_sold"]] = 999999
    again = create_model(model, "D", 7, 7, parameter_grid(model, False, 1)[0], 100).fit(
        frame.iloc[:100]
    )
    np.testing.assert_allclose(again.predict(7), forecast)
    save_artifact(tmp_path, model, fitted, {})
    np.testing.assert_allclose(load_artifact(tmp_path, model).predict(7), forecast)


@pytest.mark.parametrize("model", ["lightgbm", "xgboost"])
def test_randomized_search_is_seeded_bounded_and_not_a_fixed_pair(model):
    a = parameter_grid(model, True, 1, trials=6, seed=42)
    assert len(a) == 6
    assert len({tuple(sorted(row.items())) for row in a}) == 6
    assert a == parameter_grid(model, True, 1, trials=6, seed=42)
    assert a != parameter_grid(model, True, 1, trials=6, seed=43)
    assert len(parameter_grid(model, False, 1, trials=6)) == 1


def test_descriptive_statistics_by_hand_and_gaps():
    periods = pd.Series([2.0, 4.0, np.nan, 8.0], index=pd.date_range("2026-01-01", periods=4))
    r = summarize_demand(periods, "D")
    assert r["mean"] == pytest.approx(14 / 3)
    assert r["median"] == 4
    assert r["standard_deviation"] == pytest.approx(np.std([2, 4, 8], ddof=1))
    assert r["missing_periods"] == 1
    assert r["trend_slope_per_period"] == pytest.approx(2)
    assert r["seasonality_detected"] is None


@pytest.mark.parametrize("values", [[np.nan], [0.0], [3.0, 3.0, 3.0]])
def test_summary_empty_zero_and_one_period_are_finite(values):
    r = summarize_demand(
        pd.Series(values, index=pd.date_range("2026-01-01", periods=len(values))), "D"
    )
    assert r["outlier_count"] == 0
    assert r["standard_deviation"] in (None, 0)
    assert r["cv"] in (None, 0)


def test_outliers_are_actual_observations_and_not_removed():
    values = [10, 11, 9, 12, 10, 11, 9, 100]
    r = summarize_demand(pd.Series(values, index=pd.date_range("2026-01-01", periods=8)), "D")
    assert r["outlier_count"] == 1
    assert r["outliers"] == [{"date": "2026-01-08", "value": 100}]
    assert r["maximum"] == 100
