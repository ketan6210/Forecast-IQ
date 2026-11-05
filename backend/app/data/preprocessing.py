from typing import Literal

import pandas as pd

from backend.app.data.validator import KEYS
from backend.app.errors import AppError


def prepare_daily_series(
    frame: pd.DataFrame,
    missing_policy: Literal["flag", "zero"] = "flag",
) -> pd.DataFrame:
    """Reindex each series independently; zero filling requires an explicit caller policy.

    Price and optional covariates are only forward-filled within each series. Initial
    unknown values remain missing. Never backfill from future observations.
    """
    if missing_policy not in {"flag", "zero"}:
        raise AppError("Unsupported missing-observation policy.")
    if frame.duplicated(KEYS).any():
        raise AppError("Resolve duplicate store/product/date observations before preprocessing.")
    parts = []
    for (store, product), group in frame.groupby(["store_id", "product_id"], sort=True):
        group = group.sort_values("date").set_index("date")
        days = pd.date_range(group.index.min(), group.index.max(), freq="D", name="date")
        daily = group.reindex(days)
        daily["store_id"], daily["product_id"] = store, product
        daily["observation_missing"] = daily.units_sold.isna()
        if missing_policy == "zero":
            daily["units_sold"] = daily.units_sold.fillna(0)
        for col in ["price", "category", "region"]:
            if col in daily:
                daily[col] = daily[col].ffill()
        # Unknown event flags remain missing, rather than carrying yesterday's event forward.
        parts.append(daily.reset_index())
    result = pd.concat(parts, ignore_index=True) if parts else frame.copy()
    result.attrs.update(frame.attrs)
    return result
