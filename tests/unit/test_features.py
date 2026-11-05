import numpy as np
import pandas as pd
import pytest

from backend.app.features.feature_engineering import FeatureEngineer


def test_lags_and_rolling_windows(series):
    features = FeatureEngineer().transform(series)
    for lag in [1, 7, 14, 28]:
        assert features.loc[35, f"sales_lag_{lag}"] == series.loc[35 - lag, "units_sold"]
        assert features[f"sales_lag_{lag}"].iloc[:lag].isna().all()
    for window in [7, 14, 28]:
        assert features.loc[35, f"rolling_mean_{window}"] == pytest.approx(
            series.units_sold.iloc[35 - window : 35].mean()
        )
    assert features.loc[35, "rolling_std_7"] == pytest.approx(series.units_sold.iloc[28:35].std())
    assert features.loc[35, "rolling_std_28"] == pytest.approx(series.units_sold.iloc[7:35].std())


@pytest.mark.parametrize("offset", [0, 1, 2, 10])
def test_current_and_future_targets_cannot_change_features_at_t(series, offset):
    """Perturb y[t], y[t+1], y[t+2] and later targets; x[t] must be identical."""
    engineer = FeatureEngineer()
    original = engineer.transform(series)
    changed = series.copy()
    t = 60
    changed.loc[t + offset :, "units_sold"] = 1_000_000 + np.arange(len(changed) - t - offset)
    actual = engineer.transform(changed)
    pd.testing.assert_frame_equal(
        original.loc[:t, engineer.columns(original)], actual.loc[:t, engineer.columns(actual)]
    )


def test_series_do_not_share_lags(series):
    second = series.copy()
    second["product_id"] = "P2"
    second["units_sold"] = 999
    frame = FeatureEngineer().transform(pd.concat([second, series]))
    first_p2 = frame[frame.product_id == "P2"].iloc[0]
    assert pd.isna(first_p2.sales_lag_1)
    assert pd.isna(first_p2.rolling_mean_7)
    assert frame[frame.product_id == "P1"].sales_lag_1.dropna().max() < 999


def test_calendar_and_price_features(series):
    frame = FeatureEngineer().transform(series)
    assert frame.day_of_week.iloc[0] == 2
    assert frame.price_lag_1.iloc[1] == 11
    assert frame.price_change.iloc[1] == -1
    assert frame.price_change_pct.iloc[1] == pytest.approx(-1 / 11)
    assert frame.is_weekend.iloc[3] == 1
