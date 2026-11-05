import numpy as np
import pandas as pd

from backend.app.models.base import Candidate


class PeriodBaseline(Candidate):
    def __init__(self, *args, name: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name

    def fit(self, history: pd.DataFrame) -> "PeriodBaseline":
        self.sales = history.units_sold.to_numpy(float)
        if self.name == "seasonal_naive" and len(self.sales) < self.season:
            raise ValueError(f"Seasonal naive requires {self.season} periods.")
        return self

    def predict(self, horizon: int) -> np.ndarray:
        if self.name == "seasonal_naive":
            return np.resize(self.sales[-self.season :], horizon)
        value = self.sales[-7:].mean() if self.name == "moving_average" else self.sales[-1]
        return np.repeat(value, horizon)
