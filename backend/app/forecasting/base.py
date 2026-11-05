from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class ForecastModel(ABC):
    """A single store/product model with a fixed-origin, multi-step forecast interface."""

    name: str

    def fit(self, history: pd.DataFrame, features: pd.DataFrame | None = None) -> "ForecastModel":
        self.history = history.copy().reset_index(drop=True)
        self.sales = self.history.units_sold.to_numpy(dtype=float)
        if not len(self.sales) or not np.isfinite(self.sales).all():
            raise ValueError("Models require finite observed sales.")
        return self

    @abstractmethod
    def predict(self, horizon: int) -> np.ndarray:
        """Forecast without receiving actual sales or covariates after the forecast origin."""
