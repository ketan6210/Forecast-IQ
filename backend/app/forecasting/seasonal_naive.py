import numpy as np

from backend.app.forecasting.base import ForecastModel


class SeasonalNaive(ForecastModel):
    name = "seasonal_naive"

    def predict(self, horizon: int) -> np.ndarray:
        if len(self.sales) < 7:
            raise ValueError("Seasonal naive needs at least seven observed days.")
        return np.resize(self.sales[-7:], horizon)
