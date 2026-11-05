import numpy as np
import pandas as pd
import pytest

from backend.app.data.diagnostics import diagnostics
from backend.app.data.frequency import future_dates, prepare_series, resolve_frequency
from backend.app.errors import AppError
from backend.app.evaluation.backtesting import make_plan, metric_summary
from backend.app.evaluation.model_selection import rank_models
from backend.app.evaluation.probabilistic_metrics import ResidualCalibrator, probabilistic_metrics
from backend.app.explainability.shap_values import explain_tree
from backend.app.features.advanced import AdvancedFeatures
from backend.app.models.base import checked
from backend.app.models.registry import create_model, parameter_grid
from backend.app.schemas.advanced import TrainingRequest
from backend.app.services.advanced_training import backtest_config, select_candidates
from backend.app.services.artifacts import load_artifact, save_artifact


def request(**kwargs):
    return TrainingRequest(
        dataset_id="test", store_id="S1", product_id="P1", horizon=7, folds=2, **kwargs
    )


@pytest.mark.parametrize(
    "frequency,expected", [("D", "D"), ("W-MON", "W-MON"), ("MS", "MS"), ("ME", "ME")]
)
def test_frequency_and_missing_periods(series, frequency, expected):
    series["date"] = pd.date_range("2015-01-01", periods=len(series), freq=frequency)
    sparse = series.drop(index=[33, 34])
    assert resolve_frequency(sparse.date) == expected
    with pytest.raises(AppError, match="Missing"):
        prepare_series(sparse, expected, "flag")
    prepared = prepare_series(sparse, expected, "zero")
    assert len(prepared) == len(series)
    assert prepared.observation_missing.sum() == 2
    assert prepared.iloc[33:35].units_sold.eq(0).all()
    assert len(future_dates(prepared.date.iloc[-1], 30, expected)) == 30


def test_month_end_calendar_boundary():
    assert future_dates(pd.Timestamp("2024-01-31"), 2, "ME").strftime("%Y-%m-%d").tolist() == [
        "2024-02-29",
        "2024-03-31",
    ]


@pytest.mark.parametrize(
    "requested,expected", [("daily", "D"), ("weekly", "W-WED"), ("monthly", "MS")]
)
def test_single_observation_explicit_frequency_is_canonical(requested, expected):
    assert resolve_frequency(pd.Series([pd.Timestamp("2025-01-01")]), requested) == expected


def test_reject_misaligned_explicit_frequency(series):
    with pytest.raises(AppError):
        resolve_frequency(series.date, "monthly")
    with pytest.raises(AppError):
        resolve_frequency(series.date, "weekly")


def test_rolling_origins_and_final_test_are_disjoint():
    req = request(window="rolling", window_size=65)
    plan = make_plan(200, req)
    for fold in plan.folds:
        assert fold.train_start < fold.train_end < fold.validation_end <= plan.calibration_start
        assert fold.train_end - fold.train_start == 65
    assert plan.calibration_start < plan.test_start < 200
    assert plan.folds[-1].validation_end == plan.calibration_start
    assert plan.folds[0].validation_end == plan.folds[1].train_end


def test_expanding_windows_start_at_zero():
    assert all(fold.train_start == 0 for fold in make_plan(200, request()).folds)


def test_insufficient_backtest_history_is_actionable():
    with pytest.raises(AppError, match="Reduce the horizon"):
        make_plan(60, request())


@pytest.mark.parametrize("offset", [0, 1, 2, 14])
def test_advanced_feature_target_leakage(series, offset):
    engineer = AdvancedFeatures()
    before = engineer.transform(series)
    perturbed = series.copy()
    perturbed.loc[70 + offset :, "units_sold"] = 98765
    after = engineer.transform(perturbed)
    pd.testing.assert_frame_equal(
        before.loc[:70, engineer.columns(before)], after.loc[:70, engineer.columns(after)]
    )
    assert before.sales_lag_2.iloc[35] == series.units_sold.iloc[33]
    assert before.sales_lag_3.iloc[35] == series.units_sold.iloc[32]
    assert before.rolling_std_14.iloc[35] == pytest.approx(series.units_sold.iloc[21:35].std())


def test_quantile_metrics_by_hand():
    values = probabilistic_metrics(np.array([10, 20]), np.array([[8, 10, 12], [15, 18, 21]]))
    assert values["pinball_p10"] == pytest.approx(0.35)
    assert values["pinball_p50"] == pytest.approx(0.5)
    assert values["pinball_p90"] == pytest.approx(0.15)
    assert values["coverage"] == 1
    assert values["mean_interval_width"] == 5


def test_coverage_is_not_hardcoded():
    metrics = probabilistic_metrics(np.array([100, 0]), np.array([[1, 2, 3], [1, 2, 3]]))
    assert metrics["coverage"] == 0


def test_residual_quantiles_are_ordered_data_driven_and_nonnegative():
    calibrator = ResidualCalibrator().fit(np.arange(-10, 10))
    result = calibrator.predict(np.array([0, 20]))
    assert (np.diff(result, axis=1) >= 0).all()
    assert (result >= 0).all()
    assert calibrator.offsets.tolist() == [-9, -0.5, 8]
    changed = ResidualCalibrator().fit(np.arange(-20, 20, 2))
    assert not np.allclose(result, changed.predict(np.array([0, 20])))


def test_crossing_quantiles_and_short_calibration_fail():
    with pytest.raises(ValueError):
        probabilistic_metrics(np.ones(2), np.array([[1, 0, 2], [1, 0, 2]]))
    with pytest.raises(ValueError):
        ResidualCalibrator().fit(np.ones(19))


def row(name, wapes):
    folds = [
        {
            "fold": i + 1,
            "metrics": {metric: value for metric in ("mae", "rmse", "wape", "smape", "mase")},
        }
        for i, value in enumerate(wapes)
    ]
    return {
        "model": name,
        "status": "ok",
        "summary": metric_summary(folds),
        "folds": folds,
        "forecast_stability": 0,
    }


def test_champion_cannot_win_on_one_lucky_fold():
    stable = row("ets", [0.2, 0.2, 0.2])
    lucky = row("xgboost", [0.01, 0.4, 0.4])
    ranked = rank_models([lucky, stable])
    assert ranked[0]["model"] == "ets"
    assert lucky["summary"]["wape"]["best_fold"] == 1
    assert lucky["summary"]["wape"]["worst_fold"] == 2
    assert lucky["summary"]["wape"]["std"] > 0


@pytest.mark.parametrize(
    "model", ["arima", "sarima", "ets", "lightgbm", "xgboost", "linear_regression"]
)
def test_advanced_models_train_forecast_and_serialize(series, model, tmp_path):
    params = parameter_grid(model, False, 1)[0]
    fitted = create_model(model, "D", 7, 14, params, len(series)).fit(series)
    values = checked(fitted, 14)
    assert len(values) == 14
    save_artifact(tmp_path, model, fitted, {"version": "test"})
    restored = load_artifact(tmp_path, model)
    np.testing.assert_allclose(values, checked(restored, 14))


@pytest.mark.parametrize("name", ["lightgbm", "xgboost"])
def test_shap_reconstructs_actual_tree_predictions(series, name):
    model = create_model(name, "D", 7, 7, parameter_grid(name, False, 1)[0], len(series)).fit(
        series
    )
    explanation = explain_tree(model, 7)
    assert len(explanation["global_importance"]) == len(model.features)
    assert len(explanation["summary_samples"]) > 0
    for point in explanation["forecast_drivers"]:
        reconstructed = point["base_value"] + sum(
            driver["shap_value"] for driver in point["drivers"]
        )
        assert reconstructed == pytest.approx(point["raw_prediction"], rel=1e-4, abs=1e-4)


def test_artifact_integrity_failure(series, tmp_path):
    model = create_model("naive", "D", 7, 7, {}, len(series)).fit(series)
    save_artifact(tmp_path, "naive", model, {})
    (tmp_path / "naive.joblib").write_bytes(b"corrupted")
    with pytest.raises(AppError, match="integrity"):
        load_artifact(tmp_path, "naive")
    with pytest.raises(AppError):
        load_artifact(tmp_path, "../../outside")


def test_neural_short_history_fallback_does_not_require_torch():
    with pytest.raises(ValueError, match="512"):
        create_model("nbeats", "D", 7, 7, {}, 200)


def test_nbeats_actual_training_and_serialization(tmp_path):
    pytest.importorskip("torch")
    n = 550
    series = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=n),
            "units_sold": 20 + 4 * np.sin(np.arange(n) * 2 * np.pi / 7),
            "store_id": "S",
            "product_id": "P",
            "price": 1.0,
        }
    )
    model = create_model("nbeats", "D", 7, 7, {"epochs": 2}, n).fit(series)
    predictions = checked(model, 7)
    assert len(model.losses) == 2
    assert np.isfinite(model.losses).all()
    save_artifact(tmp_path, "nbeats", model, {})
    np.testing.assert_allclose(predictions, checked(load_artifact(tmp_path, "nbeats"), 7))


def test_test_and_calibration_mutation_cannot_change_tuning_or_selection(series):
    req = request(models=["lightgbm", "xgboost"], tune=True)
    plan = make_plan(len(series), req)
    original = select_candidates(series, req, plan, "D")
    changed = series.copy()
    changed.loc[plan.calibration_start :, ["units_sold", "price", "promotion"]] = 99999
    after = select_candidates(changed, req, plan, "D")
    assert rank_models(original)[0]["model"] == rank_models(after)[0]["model"]
    for first, second in zip(original, after, strict=True):
        assert first["parameters"] == second["parameters"]
        assert first["summary"] == second["summary"]
        assert first["folds"] == second["folds"]


def test_training_imputer_does_not_see_validation_price(series):
    req = request(models=["linear_regression"])
    plan = make_plan(len(series), req)
    first = backtest_config(series, plan, req, "linear_regression", {}, "D")
    changed = series.copy()
    origin = plan.folds[0].train_end
    changed.loc[origin:, "price"] = 50000
    after = backtest_config(changed, plan, req, "linear_regression", {}, "D")
    assert first["folds"][0]["predictions"] == after["folds"][0]["predictions"]


def test_diagnostics_constant_series_are_finite(series):
    series["units_sold"] = 0
    result = diagnostics(series, "D")
    assert result["acf"] == result["pacf"] == []
    assert result["outlier_count"] == 0
    assert result["trend"] == "flat"
