"""Forecast-origin assumptions for explicitly selected numeric external predictors."""

import numpy as np
import pandas as pd


def latest_covariates(history: pd.DataFrame) -> dict[str, float]:
    """Use only the training prefix; no holdout feature values enter a recursive forecast."""
    result = {}
    for name in history.attrs.get("external_features", []):
        known = history[name].dropna()
        result[name] = float(known.iloc[-1]) if len(known) else np.nan
    return result
