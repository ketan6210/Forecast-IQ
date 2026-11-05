import numpy as np

from backend.app.forecasting.base import ForecastModel


class NaiveForecast(ForecastModel):
    name = "naive"

    def predict(self, horizon: int) -> np.ndarray:
        return np.repeat(self.sales[-1], horizon)
