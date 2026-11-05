import csv
import io

import pandas as pd

from backend.app.config import settings
from backend.app.errors import AppError


def read_csv(content: bytes) -> pd.DataFrame:
    """Read bounded UTF-8 CSV while retaining string identifiers and rejecting ambiguous headers."""
    if not content.strip():
        raise AppError("The CSV is empty.")
    try:
        text = content.decode("utf-8-sig")
        if "\x00" in text:
            raise AppError("The file contains binary data. Upload a UTF-8 CSV.")
        reader = csv.reader(io.StringIO(text), strict=True)
        header = next(reader)
        if len(header) != len(set(header)) or any(not col or col != col.strip() for col in header):
            raise AppError(
                "CSV column names must be unique, nonempty and have no surrounding spaces."
            )
        for line_number, row in enumerate(reader, start=2):
            if row and len(row) != len(header):
                raise AppError(
                    f"CSV row {line_number} has {len(row)} fields; expected {len(header)}."
                )
            if line_number > settings.max_dataset_rows + 1:
                raise AppError(f"Dataset exceeds the {settings.max_dataset_rows:,}-row limit.", 413)
        df = pd.read_csv(
            io.StringIO(text),
            dtype="string",
            nrows=settings.max_dataset_rows + 1,
        )
    except (
        csv.Error,
        UnicodeDecodeError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
        StopIteration,
    ) as exc:
        raise AppError(
            "Cannot parse CSV. Use UTF-8, a header row, and comma-separated fields."
        ) from exc
    if len(df) > settings.max_dataset_rows:
        raise AppError(f"Dataset exceeds the {settings.max_dataset_rows:,}-row limit.", 413)
    return df
