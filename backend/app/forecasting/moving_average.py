import numpy as np

from backend.app.forecasting.base import ForecastModel


class MovingAverage(ForecastModel):
    name = "moving_average"

    def predict(self, horizon: int) -> np.ndarray:
        # A fixed-origin seven-day mean; unknown future observations never enter the window.
        return np.repeat(self.sales[-7:].mean(), horizon)
