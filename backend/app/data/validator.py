import numpy as np
import pandas as pd

from backend.app.data.frequency import resolve_frequency
from backend.app.errors import AppError
from backend.app.schemas.datasets import ValidationReport

REQUIRED = {"date", "store_id", "product_id", "units_sold"}
KEYS = ["store_id", "product_id", "date"]
MIN_HISTORY = 90


class DataValidator:
    """Validate calendar-period observations before deduplication or forecasting."""

    def validate(
        self, source: pd.DataFrame, frequency: str = "D", external_features: list[str] | None = None
    ) -> tuple[pd.DataFrame, ValidationReport]:
        df = source.copy()
        external_features = list(external_features or [])
        reserved = REQUIRED | {
            "price",
            "promotion",
            "discount",
            "holiday",
            "inventory",
            "category",
            "region",
            "sku_id",
            "on_hand_inventory",
            "on_order_inventory",
            "backorders",
            "day_of_week",
            "day_of_month",
            "week_of_year",
            "month",
            "quarter",
            "year",
            "is_weekend",
        }
        invalid_features = [
            c
            for c in external_features
            if c not in df or c in reserved or c.startswith(("sales_lag_", "rolling_", "price_"))
        ]
        if (
            invalid_features
            or len(external_features) > 20
            or len(set(external_features)) != len(external_features)
        ):
            raise AppError(
                "Select at most 20 unique additional numeric predictor columns; "
                "identifiers, demand and inventory cannot be predictors. "
                f"Invalid selections: {invalid_features}."
            )
        # Unknown price stays missing; it is never replaced with a business assumption.
        if "price" not in df:
            df["price"] = np.nan
        for col in df.select_dtypes(include=["object", "string"]):
            blanks = df[col].map(lambda value: isinstance(value, str) and not value.strip())
            df.loc[blanks, col] = pd.NA
        report = ValidationReport(row_count=len(df))
        report.external_features = external_features
        missing = sorted(REQUIRED - set(df.columns))
        if missing:
            report.errors.append(f"Missing required columns: {', '.join(missing)}.")
        if df.empty:
            report.errors.append("The dataset is empty. Include at least one row of observations.")
        if report.errors:
            report.validation_status = "FAIL"
            return df, report

        for col in ["store_id", "product_id", "category", "region"]:
            if col in df:
                df[col] = df[col].astype("string").str.strip().replace("", pd.NA)
        report.missing_value_summary = {col: int(df[col].isna().sum()) for col in df}
        report.missing_rate = float(df.isna().sum().sum() / df.size)
        report.duplicate_count = int(df.duplicated().sum())
        for col, count in report.missing_value_summary.items():
            if count:
                report.warnings.append(f"{count / len(df):.1%} of {col} values are missing.")
        for col in ["store_id", "product_id"]:
            if df[col].isna().any():
                report.errors.append(f"{col} must be present on every observation.")

        dates = pd.to_datetime(df.date, errors="coerce", format="mixed", utc=True)
        report.invalid_date_count = int(dates.isna().sum())
        if report.invalid_date_count:
            report.errors.append(f"{report.invalid_date_count} dates are missing or invalid.")
        if ((dates != dates.dt.normalize()) & dates.notna()).any():
            report.errors.append("Use calendar dates (YYYY-MM-DD), without a time of day.")
        df["date"] = dates.dt.tz_localize(None).dt.normalize()

        numeric = [
            "units_sold",
            "price",
            "promotion",
            "discount",
            "inventory",
            "holiday",
            *external_features,
        ]
        for col in numeric:
            if col not in df:
                continue
            values = pd.to_numeric(df[col], errors="coerce").astype(float)
            invalid = (df[col].notna() & values.isna()) | np.isinf(values)
            if invalid.any():
                report.errors.append(
                    f"{col} contains {int(invalid.sum())} non-finite/nonnumeric values."
                )
            df[col] = values
        report.negative_sales_count = int((df.units_sold < 0).sum())
        report.invalid_price_count = int((df.price <= 0).sum())
        if report.negative_sales_count:
            report.errors.append("units_sold cannot be negative.")
        if report.invalid_price_count:
            report.errors.append("Nonmissing price values must be greater than zero.")
        for col in ["units_sold", *external_features]:
            if df[col].notna().sum() == 0:
                report.errors.append(f"{col} has no valid observations.")
        for col in ["promotion", "holiday"]:
            if col in df and (~df[col].dropna().isin([0, 1])).any():
                report.errors.append(f"{col} must be 0 or 1 when present.")
        if "discount" in df and ((df.discount < 0) | (df.discount > 1)).any():
            report.errors.append("discount must be a fraction between 0 and 1.")
        if "inventory" in df and (df.inventory < 0).any():
            report.errors.append("inventory cannot be negative.")

        # Equivalent date/numeric spellings may become duplicates during normalization.
        # Account for every removed row in the quality report.
        report.duplicate_count = int(df.duplicated().sum())
        df = df.drop_duplicates()
        report.duplicate_observation_count = int(df.duplicated(KEYS).sum())
        if report.duplicate_count:
            report.warnings.append(f"Removed {report.duplicate_count} exact duplicate rows.")
        if report.duplicate_observation_count:
            report.errors.append(
                "Conflicting store/product/date observations; aggregate or fix them."
            )
        report.store_count = int(df.store_id.nunique())
        report.product_count = int(df.product_id.nunique())
        report.category_count = int(df.category.nunique()) if "category" in df else None
        if df.date.notna().any():
            report.date_min = df.date.min().date().isoformat()
            report.date_max = df.date.max().date().isoformat()
        short_series = []
        frequencies = set()
        for (store, product), group in df.groupby(["store_id", "product_id"]):
            days = group.date.dropna()
            if not days.is_monotonic_increasing:
                report.chronologically_ordered = False
            if days.empty:
                continue
            span = (days.max() - days.min()).days + 1
            if span > 10_000:
                report.errors.append(f"{store}/{product} exceeds the supported 10,000-day span.")
            try:
                detected = resolve_frequency(days, frequency)
                frequencies.add(detected)
                expected = pd.date_range(days.min(), days.max(), freq=detected)
                report.missing_date_count += max(0, len(expected) - days.nunique())
            except AppError as exc:
                report.errors.append(f"{store}/{product}: {exc.message}")
            if group.units_sold.notna().sum() < MIN_HISTORY:
                short_series.append(
                    f"{store}/{product} ({group.units_sold.notna().sum()} observations)"
                )
        if short_series:
            report.warnings.append(
                f"{len(short_series)} series have fewer than {MIN_HISTORY} observed periods: "
                + ", ".join(short_series[:10])
                + "."
            )
        if not report.chronologically_ordered:
            report.warnings.append(
                "Input was out of order; observations were sorted chronologically."
            )
        if report.missing_date_count:
            report.warnings.append(
                f"{report.missing_date_count} expected observations are absent. "
                "Missing sales stay flagged "
                "unless you explicitly confirm they represent zero demand."
            )
        report.processed_row_count = len(df)
        report.frequency = next(iter(frequencies)) if len(frequencies) == 1 else "mixed"
        report.validation_status = (
            "FAIL" if report.errors else "PASS_WITH_WARNINGS" if report.warnings else "PASS"
        )
        cleaned = df.sort_values(KEYS).reset_index(drop=True)
        cleaned.attrs.update(external_features=external_features, frequency=report.frequency)
        return cleaned, report
