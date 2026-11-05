import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from backend.app.data.diagnostics import diagnostics
from backend.app.models.base import Candidate


class StatisticalModel(Candidate):
    def __init__(self, *args, name: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name

    def fit(self, history: pd.DataFrame) -> "StatisticalModel":
        y = history.units_sold.to_numpy(float)
        info = diagnostics(history, self.frequency)
        seasonal = info["seasonality_detected"]
        trend = info["trend"] != "flat"
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            if self.name == "ets":
                self.fitted_params = {
                    "trend": "add" if trend else None,
                    "seasonal": "add" if seasonal else None,
                    "seasonal_periods": self.season if seasonal else None,
                }
                self.fitted = ExponentialSmoothing(
                    y,
                    **self.fitted_params,
                    initialization_method="estimated",
                    damped_trend=trend,
                ).fit(optimized=True, use_brute=False)
            else:
                order = (1, int(trend), 1)
                seasonal_order = (
                    (1, 0, 0, self.season) if self.name == "sarima" and seasonal else (0, 0, 0, 0)
                )
                self.fitted_params = {"order": order, "seasonal_order": seasonal_order}
                self.fitted = ARIMA(y, **self.fitted_params).fit(method_kwargs={"maxiter": 80})
                if not self.fitted.mle_retvals.get("converged", True):
                    raise ValueError("Statistical optimizer did not converge within 80 iterations.")
                if self.name == "sarima" and not seasonal:
                    self.notes.append(
                        "No supported seasonal pattern in this training window; "
                        "adapted to nonseasonal ARIMA."
                    )
            self.notes += sorted({str(w.message) for w in captured})[:5]
        return self

    def predict(self, horizon: int) -> np.ndarray:
        return np.maximum(0, np.asarray(self.fitted.forecast(horizon), float))
