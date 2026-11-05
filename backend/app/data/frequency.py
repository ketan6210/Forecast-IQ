"""Explicit daily, anchored weekly and calendar-month frequency handling."""

import pandas as pd

from backend.app.errors import AppError

WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def resolve_frequency(dates: pd.Series, requested: str = "auto") -> str:
    values = pd.DatetimeIndex(pd.to_datetime(dates).dropna().unique()).sort_values()
    if not len(values):
        raise AppError("Frequency detection requires at least one valid date.")
    if requested in {"auto", "monthly", "MS", "ME"}:
        if values.is_month_start.all():
            detected = "MS"
        elif values.is_month_end.all():
            detected = "ME"
        else:
            detected = ""
        if requested in {"monthly", "MS", "ME"}:
            if not detected or (requested != "monthly" and requested != detected):
                raise AppError("Monthly data must use consistent month-start or month-end dates.")
            return detected
        if detected and len(values) >= 3:
            return detected
    weekday = values.dayofweek
    if requested == "weekly" or requested.startswith("W-"):
        if len(set(weekday)) != 1:
            raise AppError("Weekly observations must use the same weekday.")
        actual = f"W-{WEEKDAYS[int(weekday[0])]}"
        if requested.startswith("W-") and requested != actual:
            raise AppError(f"Weekly dates do not align with {requested}.")
        return actual
    if requested == "auto" and len(values) >= 3 and len(set(weekday)) == 1:
        return f"W-{WEEKDAYS[int(weekday[0])]}"
    if requested not in {"auto", "D", "daily"}:
        raise AppError("Supported frequencies are daily, weekly, and month-start/month-end.")
    return "D"


def seasonal_period(frequency: str) -> int:
    return 7 if frequency == "D" else 52 if frequency.startswith("W-") else 12


def future_dates(last: pd.Timestamp, horizon: int, frequency: str) -> pd.DatetimeIndex:
    return pd.date_range(last, periods=horizon + 1, freq=frequency)[1:]


def prepare_series(frame: pd.DataFrame, frequency: str, missing_policy: str) -> pd.DataFrame:
    """Reindex one series without backfill; only explicit zero policy fills target gaps."""
    frame = frame.sort_values("date").copy()
    if frame.date.duplicated().any():
        raise AppError("The selected series contains duplicate dates.")
    index = pd.date_range(frame.date.min(), frame.date.max(), freq=frequency, name="date")
    if not frame.date.isin(index).all():
        raise AppError("Some observations do not align with the selected frequency.")
    result = frame.set_index("date").reindex(index)
    result["store_id"] = frame.store_id.iloc[0]
    result["product_id"] = frame.product_id.iloc[0]
    result["observation_missing"] = result.units_sold.isna()
    if missing_policy == "zero":
        result["units_sold"] = result.units_sold.fillna(0)
    elif result.units_sold.isna().any():
        raise AppError(
            "Missing demand periods are flagged. "
            "Supply observations or explicitly confirm zero sales."
        )
    result["price"] = result.price.ffill()
    result = result.reset_index()
    result.attrs.update(frame.attrs)
    return result
