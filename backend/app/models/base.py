from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class Candidate(ABC):
    name: str

    def __init__(self, frequency: str, season: int, horizon: int, **params):
        self.frequency, self.season, self.horizon = frequency, season, horizon
        self.params = params
        self.fitted_params: dict = {}
        self.features: list[str] = []
        self.notes: list[str] = []

    @abstractmethod
    def fit(self, history: pd.DataFrame) -> "Candidate":
        pass

    @abstractmethod
    def predict(self, horizon: int) -> np.ndarray:
        pass


def checked(model: Candidate, horizon: int) -> np.ndarray:
    values = np.asarray(model.predict(horizon), float)
    if values.shape != (horizon,) or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError(f"{model.name} returned invalid predictions.")
    return values
