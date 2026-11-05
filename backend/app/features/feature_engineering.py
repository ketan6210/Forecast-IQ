import pandas as pd


class FeatureEngineer:
    """Construct per-series daily features. Every target-derived feature is shifted."""

    lags = (1, 2, 3, 7, 14, 28)
    windows = (7, 14, 28)

    def __init__(self, external_features: list[str] | None = None):
        self.external_features = list(external_features or [])

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        df = frame.sort_values(["store_id", "product_id", "date"]).reset_index(drop=True).copy()
        dates = pd.to_datetime(df.date)
        df["day_of_week"] = dates.dt.dayofweek
        df["day_of_month"] = dates.dt.day
        df["week_of_year"] = dates.dt.isocalendar().week.astype(int)
        df["month"] = dates.dt.month
        df["quarter"] = dates.dt.quarter
        df["year"] = dates.dt.year
        df["is_weekend"] = (dates.dt.dayofweek >= 5).astype(int)
        sales = df.groupby(["store_id", "product_id"], sort=False).units_sold
        for lag in self.lags:
            df[f"sales_lag_{lag}"] = sales.shift(lag)
        for window in self.windows:
            df[f"rolling_mean_{window}"] = sales.transform(
                lambda s: s.shift(1).rolling(window, min_periods=window).mean()
            )
        for window in self.windows:
            df[f"rolling_std_{window}"] = sales.transform(
                lambda s: s.shift(1).rolling(window, min_periods=window).std()
            )
        df["price_lag_1"] = df.groupby(["store_id", "product_id"]).price.shift(1)
        df["price_change"] = df.price - df.price_lag_1
        df["price_change_pct"] = df.price_change / df.price_lag_1
        return df

    def columns(self, frame: pd.DataFrame) -> list[str]:
        base = [
            "day_of_week",
            "day_of_month",
            "week_of_year",
            "month",
            "quarter",
            "year",
            "is_weekend",
            "price",
            "price_lag_1",
            "price_change",
            "price_change_pct",
        ]
        base += [f"sales_lag_{lag}" for lag in self.lags]
        base += [f"rolling_mean_{window}" for window in self.windows]
        base += [f"rolling_std_{window}" for window in self.windows]
        extras = getattr(self, "external_features", []) or frame.attrs.get("external_features", [])
        return base + [c for c in ("promotion", "discount", "holiday") if c in frame] + extras
