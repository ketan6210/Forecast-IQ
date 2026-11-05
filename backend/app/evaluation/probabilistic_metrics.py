import numpy as np


def probabilistic_metrics(actual: np.ndarray, quantiles: np.ndarray) -> dict[str, float]:
    actual, quantiles = np.asarray(actual, float), np.asarray(quantiles, float)
    if actual.ndim != 1 or quantiles.shape != (len(actual), 3) or not len(actual):
        raise ValueError("Expected actuals and a nonempty n×3 quantile matrix.")
    if not np.isfinite(actual).all() or not np.isfinite(quantiles).all():
        raise ValueError("Probabilistic metrics require finite observations.")
    if (np.diff(quantiles, axis=1) < 0).any():
        raise ValueError("Quantiles must be ordered P10 ≤ P50 ≤ P90.")
    result = {}
    for i, level in enumerate((0.1, 0.5, 0.9)):
        residual = actual - quantiles[:, i]
        result[f"pinball_p{int(level * 100)}"] = float(
            np.maximum(level * residual, (level - 1) * residual).mean()
        )
    result["coverage"] = float(((actual >= quantiles[:, 0]) & (actual <= quantiles[:, 2])).mean())
    result["mean_interval_width"] = float((quantiles[:, 2] - quantiles[:, 0]).mean())
    return result


class ResidualCalibrator:
    """Finite-rank corrected signed residual quantiles from separate prequential forecasts.

    These are marginal empirical quantiles, pooled across forecast leads. Temporal
    dependence and refitting preclude an unconditional exchangeability guarantee.
    No residual from the final test block is accepted by the training service.
    """

    def fit(self, residuals: np.ndarray) -> "ResidualCalibrator":
        values = np.sort(np.asarray(residuals, float))
        if len(values) < 20 or not np.isfinite(values).all():
            raise ValueError("At least 20 finite held-out calibration residuals are required.")
        low = max(0, int(np.floor((len(values) + 1) * 0.1)) - 1)
        high = min(len(values) - 1, int(np.ceil((len(values) + 1) * 0.9)) - 1)
        self.offsets = np.array([values[low], np.median(values), values[high]])
        self.residual_count = len(values)
        return self

    def predict(self, points: np.ndarray) -> np.ndarray:
        return np.maximum(0, np.asarray(points)[:, None] + self.offsets[None, :])
