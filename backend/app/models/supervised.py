import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backend.app.data.frequency import future_dates
from backend.app.features.advanced import AdvancedFeatures
from backend.app.features.covariates import latest_covariates
from backend.app.models.base import Candidate


class SupervisedModel(Candidate):
    """Recursive point forecasts; future price/events never come from a holdout frame."""

    name = "linear_regression"

    def estimator(self):
        return make_pipeline(StandardScaler(), LinearRegression())

    def fit(self, history: pd.DataFrame) -> "SupervisedModel":
        self.history = history.copy().reset_index(drop=True)
        self.engineer = AdvancedFeatures(self.history.attrs.get("external_features", []))
        frame = self.engineer.transform(self.history)
        self.features = self.engineer.columns(frame)
        usable = frame.sales_lag_28.notna()
        if usable.sum() < 20:
            raise ValueError(
                "Supervised models require 20 training rows after 28-period lag warmup."
            )
        self.imputer = SimpleImputer(strategy="median", keep_empty_features=True)
        x = self.imputer.fit_transform(frame.loc[usable, self.features])
        self.training_features = x[-200:]
        self.regressor = self.estimator()
        self.regressor.fit(x, frame.loc[usable, "units_sold"].to_numpy(float))
        self.fitted_params = self.params.copy()
        return self

    def predict(self, horizon: int) -> np.ndarray:
        history = self.history.tail(28).copy()
        price = (
            float(self.history.price.dropna().iloc[-1])
            if self.history.price.notna().any()
            else np.nan
        )
        predictions, feature_rows = [], []
        covariates = latest_covariates(self.history)
        for date in future_dates(self.history.date.iloc[-1], horizon, self.frequency):
            row = {
                "date": date,
                "units_sold": np.nan,
                "price": price,
                "store_id": self.history.store_id.iloc[-1],
                "product_id": self.history.product_id.iloc[-1],
            }
            row.update({key: 0 for key in ("promotion", "discount", "holiday") if key in history})
            row.update(covariates)
            history = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
            features = self.engineer.transform(history).tail(1)[self.features]
            x = self.imputer.transform(features)
            value = float(self.regressor.predict(x)[0])
            if not np.isfinite(value):
                raise ValueError("Non-finite recursive prediction.")
            prediction = max(0, value)
            predictions.append(prediction)
            feature_rows.append(x[0])
            history.loc[history.index[-1], "units_sold"] = prediction
            history = history.tail(28).reset_index(drop=True)
        self.forecast_features = np.asarray(feature_rows)
        return np.array(predictions)
