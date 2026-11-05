from dataclasses import dataclass

import pandas as pd

from backend.app.errors import AppError


@dataclass
class TimeSeriesSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame

    def boundaries(self) -> dict[str, dict[str, str | int]]:
        return {
            name: {
                "start": part.date.min().date().isoformat(),
                "end": part.date.max().date().isoformat(),
                "days": part.date.nunique(),
            }
            for name, part in (
                ("train", self.train),
                ("validation", self.validation),
                ("test", self.test),
            )
        }


class TimeSeriesSplitter:
    """Split distinct dates 70/15/15 so no timestamp crosses partition boundaries."""

    def split(self, frame: pd.DataFrame) -> TimeSeriesSplit:
        dates = sorted(frame.date.unique())
        if len(dates) < 90:
            raise AppError("At least 90 daily observations are required for baseline evaluation.")
        train_end, val_end = int(len(dates) * 0.70), int(len(dates) * 0.85)
        ordered = frame.sort_values("date").reset_index(drop=True)
        return TimeSeriesSplit(
            ordered[ordered.date < dates[train_end]].copy(),
            ordered[(ordered.date >= dates[train_end]) & (ordered.date < dates[val_end])].copy(),
            ordered[ordered.date >= dates[val_end]].copy(),
        )
