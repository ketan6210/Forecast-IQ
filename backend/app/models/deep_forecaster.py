"""Compact generic N-BEATS: learned backcast/forecast bases and doubly residual blocks.

Imported only for eligible histories. This is a small CPU reference implementation,
not a reproduction of the large ensembles or accuracy claims in the N-BEATS paper.
"""

import numpy as np
import pandas as pd
import torch
from torch import nn

from backend.app.models.base import Candidate


class NBeatsBlock(nn.Module):
    def __init__(self, lookback: int, horizon: int, hidden: int = 64):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(lookback, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.backcast = nn.Linear(hidden, lookback)
        self.forecast = nn.Linear(hidden, horizon)

    def forward(self, x):
        theta = self.network(x)
        return self.backcast(theta), self.forecast(theta)


class NBeatsNetwork(nn.Module):
    def __init__(self, lookback: int, horizon: int):
        super().__init__()
        self.blocks = nn.ModuleList([NBeatsBlock(lookback, horizon) for _ in range(3)])

    def forward(self, x):
        residual = x
        forecasts = []
        for block in self.blocks:
            backcast, forecast = block(residual)
            residual = residual - backcast
            forecasts.append(forecast)
        return torch.stack(forecasts).sum(dim=0)


class NBeatsModel(Candidate):
    name = "nbeats"
    minimum_history = 512

    def fit(self, history: pd.DataFrame) -> "NBeatsModel":
        if len(history) < self.minimum_history:
            raise ValueError(f"N-BEATS requires at least {self.minimum_history} training periods.")
        lookback = max(28, 2 * self.horizon)
        values = history.units_sold.to_numpy(np.float32)
        self.scale = max(float(np.std(values)), 1.0)
        self.center = float(np.mean(values))
        scaled = (values - self.center) / self.scale
        windows = np.lib.stride_tricks.sliding_window_view(scaled, lookback + self.horizon).copy()
        x = torch.tensor(windows[:, :lookback])
        y = torch.tensor(windows[:, lookback:])
        self.last_window = scaled[-lookback:].copy()
        torch.set_num_threads(1)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(42)
            self.network = NBeatsNetwork(lookback, self.horizon)
            optimizer = torch.optim.Adam(self.network.parameters(), lr=0.001)
            epochs = self.params.get("epochs", 12)
            self.losses = []
            for _ in range(epochs):
                losses = []
                # Contiguous batches retain time order; all windows stop within this training fold.
                for start in range(0, len(x), 64):
                    optimizer.zero_grad()
                    loss = nn.functional.mse_loss(
                        self.network(x[start : start + 64]), y[start : start + 64]
                    )
                    loss.backward()
                    nn.utils.clip_grad_norm_(self.network.parameters(), 1.0)
                    optimizer.step()
                    losses.append(float(loss.detach()))
                self.losses.append(float(np.mean(losses)))
        self.network.eval()
        self.fitted_params = {
            "lookback": lookback,
            "horizon": self.horizon,
            "epochs": epochs,
            "blocks": 3,
            "hidden": 64,
            "seed": 42,
            "final_training_loss": self.losses[-1],
        }
        return self

    def predict(self, horizon: int) -> np.ndarray:
        if horizon > self.horizon:
            raise ValueError("Requested horizon exceeds the trained neural output horizon.")
        with torch.no_grad():
            values = self.network(torch.tensor(self.last_window).unsqueeze(0)).numpy()[0]
        return np.maximum(0, values[:horizon] * self.scale + self.center)
