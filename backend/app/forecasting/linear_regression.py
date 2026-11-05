from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backend.app.features.covariates import latest_covariates
from backend.app.features.feature_engineering import FeatureEngineer
from backend.app.forecasting.base import ForecastModel


class LinearRegressionForecast(ForecastModel):
    name = "linear_regression"

    def fit(self, history: pd.DataFrame, features: pd.DataFrame | None = None) -> "ForecastModel":
        super().fit(history, features)
        self.engineer = FeatureEngineer(self.history.attrs.get("external_features", []))
        features = features if features is not None else self.engineer.transform(self.history)
        self.feature_columns = self.engineer.columns(features)
        usable = features.sales_lag_28.notna()
        if usable.sum() < 20:
            raise ValueError("Linear regression needs at least 20 training rows after 28-day lags.")
        self.pipeline = make_pipeline(
            SimpleImputer(strategy="median", keep_empty_features=True),
            StandardScaler(),
            LinearRegression(),
        )
        self.pipeline.fit(
            features.loc[usable, self.feature_columns], features.loc[usable, "units_sold"]
        )
        return self

    def predict(self, horizon: int) -> np.ndarray:
        """Recursively use predictions, last known price and zero future event indicators.

        Neither holdout demand nor realized future prices/promotions are accepted as input.
        Unknown historical covariates are imputed with training-only medians.
        """
        history = self.history.tail(28).copy()
        predictions = []
        covariates = latest_covariates(self.history)
        price = (
            float(self.history.price.dropna().iloc[-1])
            if self.history.price.notna().any()
            else np.nan
        )
        for _ in range(horizon):
            row = {
                "date": history.date.iloc[-1] + timedelta(days=1),
                "store_id": history.store_id.iloc[-1],
                "product_id": history.product_id.iloc[-1],
                "units_sold": np.nan,
                "price": price,
            }
            row.update({col: 0.0 for col in ("promotion", "discount", "holiday") if col in history})
            row.update(covariates)
            history = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
            features = self.engineer.transform(history).tail(1)
            value = float(self.pipeline.predict(features[self.feature_columns])[0])
            if not np.isfinite(value):
                raise ValueError("Linear regression produced a non-finite prediction.")
            value = max(0.0, value)
            predictions.append(value)
            history.loc[history.index[-1], "units_sold"] = value
            history = history.tail(28).reset_index(drop=True)
        return np.array(predictions)
