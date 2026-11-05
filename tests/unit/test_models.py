import numpy as np
import pandas as pd
import pytest

from backend.app.forecasting.trainer import MODEL_REGISTRY, train_baselines


@pytest.mark.parametrize("horizon", [7, 14, 28])
@pytest.mark.parametrize("name", list(MODEL_REGISTRY))
def test_all_models_have_finite_nonnegative_horizon(series, name, horizon):
    model = MODEL_REGISTRY[name]().fit(series)
    predictions = model.predict(horizon)
    assert len(predictions) == horizon
    assert np.isfinite(predictions).all()
    assert (predictions >= 0).all()


def test_baseline_values(series):
    naive = MODEL_REGISTRY["naive"]().fit(series).predict(14)
    seasonal = MODEL_REGISTRY["seasonal_naive"]().fit(series).predict(14)
    average = MODEL_REGISTRY["moving_average"]().fit(series).predict(7)
    np.testing.assert_array_equal(naive, np.repeat(series.units_sold.iloc[-1], 14))
    np.testing.assert_array_equal(seasonal, np.tile(series.units_sold.iloc[-7:], 2))
    np.testing.assert_array_equal(average, np.repeat(series.units_sold.tail(7).mean(), 7))


def test_test_targets_and_covariates_cannot_affect_validation_selection(series):
    """Holdout mutation is an explicit regression test against model-selection leakage."""
    original = train_baselines(series, {})
    changed = series.copy()
    changed.loc[int(len(series) * 0.85) :, ["units_sold", "price", "promotion"]] = 9999
    perturbed = train_baselines(changed, {})
    assert original.model.name == perturbed.model.name
    for before, after in zip(original.comparison, perturbed.comparison, strict=True):
        assert before.validation_metrics == after.validation_metrics


def test_linear_forecast_repeats_without_mutating_fitted_history(series):
    model = MODEL_REGISTRY["linear_regression"]().fit(series)
    saved = model.history.copy()
    np.testing.assert_allclose(model.predict(28), model.predict(28))
    pd.testing.assert_frame_equal(saved, model.history)


def test_all_zero_training_uses_explicit_fallback(series):
    series["units_sold"] = 0
    trained = train_baselines(series, {})
    assert trained.model.name == "naive"
    assert "undefined" in trained.selection_reason
    for row in trained.comparison:
        assert row.test_metrics.wape is None
        assert row.validation_metrics.mase is None
