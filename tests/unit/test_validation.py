import numpy as np
import pandas as pd
import pytest

from backend.app.data.loader import read_csv
from backend.app.data.preprocessing import prepare_daily_series
from backend.app.data.validator import DataValidator
from backend.app.errors import AppError


def test_clean_data_passes(series):
    cleaned, report = DataValidator().validate(series)
    assert report.validation_status == "PASS"
    assert report.row_count == len(cleaned) == 140
    assert report.date_min == "2025-01-01"


@pytest.mark.parametrize("column", ["date", "store_id", "product_id", "units_sold"])
def test_required_columns(series, column):
    _, report = DataValidator().validate(series.drop(columns=column))
    assert report.validation_status == "FAIL"
    assert column in report.errors[0]


@pytest.mark.parametrize(
    "column,value",
    [
        ("date", "not-a-date"),
        ("date", "2025-02-30"),
        ("date", "2025-01-01T14:00:00"),
        ("units_sold", -1),
        ("price", 0),
        ("price", -3),
        ("price", "bad"),
        ("units_sold", float("inf")),
        ("store_id", None),
        ("product_id", " "),
        ("promotion", 2),
        ("discount", 1.5),
        ("holiday", -1),
        ("inventory", -2),
    ],
)
def test_invalid_values_fail(series, column, value):
    series[column] = (
        series[column].astype(object)
        if column in series
        else pd.Series(0, index=series.index, dtype=object)
    )
    series.loc[0, column] = value
    _, report = DataValidator().validate(series)
    assert report.validation_status == "FAIL", report


def test_exact_duplicates_removed_with_warning(series):
    cleaned, report = DataValidator().validate(pd.concat([series, series.iloc[:2]]))
    assert report.duplicate_count == 2
    assert report.processed_row_count == 140
    assert len(cleaned) == 140
    assert report.validation_status == "PASS_WITH_WARNINGS"


def test_conflicting_daily_observations_fail(series):
    conflict = series.iloc[:1].copy()
    conflict["units_sold"] = 999
    _, report = DataValidator().validate(pd.concat([series, conflict]))
    assert report.validation_status == "FAIL"
    assert report.duplicate_observation_count == 1


def test_unsorted_and_short_history_warn(series):
    cleaned, report = DataValidator().validate(series.iloc[:18].iloc[::-1])
    assert not report.chronologically_ordered
    assert report.validation_status == "PASS_WITH_WARNINGS"
    assert any("18 observations" in warning for warning in report.warnings)
    assert cleaned.date.is_monotonic_increasing


def test_missing_sales_and_prices_are_not_silently_filled(series):
    series.loc[3, "units_sold"] = np.nan
    series.loc[0, "price"] = np.nan
    cleaned, report = DataValidator().validate(series.drop(index=5))
    assert report.missing_date_count == 1
    assert report.missing_value_summary["price"] == 1
    daily = prepare_daily_series(cleaned)
    assert daily.units_sold.isna().sum() == 2
    assert daily.observation_missing.sum() == 2
    assert np.isnan(daily.loc[0, "price"])  # No future price backfill.
    zero = prepare_daily_series(cleaned, "zero")
    assert zero.loc[[3, 5], "units_sold"].tolist() == [0, 0]
    assert zero.observation_missing.sum() == 2


def test_preprocessing_isolated_by_series(series):
    other = series.copy()
    other["product_id"] = "P2"
    other["price"] = 99
    other = other.drop(index=8)
    daily = prepare_daily_series(pd.concat([series, other]))
    assert daily.groupby("product_id").size().tolist() == [140, 140]
    assert daily[daily.product_id == "P2"].price.eq(99).all()


def test_numeric_identifiers_preserve_leading_zeros():
    df = read_csv(b"date,store_id,product_id,units_sold,price\n2025-01-01,001,0002,2,9\n")
    assert df.store_id.iloc[0] == "001"
    assert df.product_id.iloc[0] == "0002"


@pytest.mark.parametrize(
    "content", [b"", b"\xff\xff", b"\x00file", b"date,date\n1,2", b'date,store_id\n"unclosed']
)
def test_invalid_csv(content):
    with pytest.raises(AppError):
        read_csv(content)


def test_all_missing_sales_fail(series):
    series["units_sold"] = np.nan
    assert DataValidator().validate(series)[1].validation_status == "FAIL"


def test_normalized_duplicate_dates_are_reported(series):
    series["date"] = series.date.astype(str)
    duplicate = series.iloc[:1].copy()
    duplicate["date"] = "2025/01/01"
    cleaned, report = DataValidator().validate(pd.concat([series, duplicate]))
    assert len(cleaned) == len(series)
    assert report.duplicate_count == 1
    assert report.validation_status == "PASS_WITH_WARNINGS"


@pytest.mark.parametrize("row", ["1,2,3", "1"])
def test_inconsistent_csv_field_count_is_rejected(row):
    with pytest.raises(AppError, match="fields"):
        read_csv(f"date,store_id\n{row}".encode())
