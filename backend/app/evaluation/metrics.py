import numpy as np

from backend.app.schemas.forecast import Metrics


def calculate_metrics(
    actual: np.ndarray,
    predicted: np.ndarray,
    training: np.ndarray,
    season: int = 7,
) -> Metrics:
    """Ratios are fractions. MASE uses only pre-origin weekly naive errors.

    WAPE and MASE are null for a zero denominator. In sMAPE, a pair of zeros
    contributes zero; other pairs use 2*absolute_error/(abs(actual)+abs(predicted)).
    """
    actual, predicted, training = [
        np.asarray(v, dtype=float) for v in (actual, predicted, training)
    ]
    if (
        actual.ndim != 1
        or predicted.shape != actual.shape
        or not actual.size
        or training.ndim != 1
        or season < 1
    ):
        raise ValueError(
            "Metrics require equal, nonempty one-dimensional arrays and a positive season."
        )
    if not all(np.isfinite(v).all() for v in (actual, predicted, training)):
        raise ValueError("Metrics require finite values.")
    errors = np.abs(actual - predicted)
    denominator = np.abs(actual).sum()
    scale = np.mean(np.abs(training[season:] - training[:-season])) if len(training) > season else 0
    paired = np.abs(actual) + np.abs(predicted)
    smape = np.divide(2 * errors, paired, out=np.zeros_like(errors), where=paired != 0).mean()
    values = dict(
        mae=float(errors.mean()),
        rmse=float(np.sqrt(np.mean(errors**2))),
        wape=float(errors.sum() / denominator) if denominator > 0 else None,
        smape=float(smape),
        mase=float(errors.mean() / scale) if scale > 0 else None,
    )
    # Very large finite inputs may overflow arithmetic; undefined results remain null.
    return Metrics(
        **{
            key: value if value is None or np.isfinite(value) else None
            for key, value in values.items()
        }
    )
