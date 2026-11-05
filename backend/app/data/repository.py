from pathlib import Path
from uuid import uuid4

import pandas as pd
from sqlalchemy.orm import Session

from backend.app.data.loader import read_csv
from backend.app.data.validator import DataValidator
from backend.app.db.models import Dataset
from backend.app.errors import AppError
from backend.app.schemas.datasets import DatasetResponse
from backend.app.timing import timed


def response_for(dataset: Dataset) -> DatasetResponse:
    return DatasetResponse(
        dataset_id=dataset.id,
        filename=dataset.filename,
        is_demo=dataset.is_demo,
        created_at=dataset.created_at.isoformat(),
        timings=dataset.timings,
        **dataset.report,
    )


def ingest(
    content: bytes,
    filename: str,
    is_demo: bool,
    session: Session,
    storage: Path,
    frequency: str = "auto",
    column_mapping: dict[str, str] | None = None,
    external_features: list[str] | None = None,
) -> Dataset:
    timings: dict[str, float] = {}
    with timed("dataset_load_seconds", timings):
        frame = read_csv(content)
        source_columns = set(frame.columns)
        mapping = dict(column_mapping or {})
        if (
            "product_id" not in frame
            and "sku_id" in frame
            and mapping.get("product_id", "product_id") == "product_id"
        ):
            mapping["product_id"] = "sku_id"
        # Recognize the complete Kaggle Store Item sales schema. Existing canonical
        # columns and explicit user mappings take priority over these aliases.
        if {"date", "store", "item", "sales"}.issubset(frame.columns):
            for canonical, alias in {
                "store_id": "store",
                "product_id": "item",
                "units_sold": "sales",
            }.items():
                if canonical not in frame and mapping.get(canonical, canonical) == canonical:
                    mapping[canonical] = alias
        renames = {}
        for canonical, source in mapping.items():
            if source == "__single__" and canonical in {"store_id", "product_id"}:
                frame[canonical] = "ALL_STORES" if canonical == "store_id" else "ALL_PRODUCTS"
            elif source != canonical:
                if source not in frame or canonical in frame or source in renames:
                    raise AppError(
                        f"Cannot map {source} to {canonical}; check column names and conflicts."
                    )
                renames[source] = canonical
        frame = frame.rename(columns=renames)
        cleaned, report = DataValidator().validate(frame, frequency, external_features)
        report.column_mapping = mapping
        if report.validation_status == "FAIL":
            message = "Dataset validation failed. " + " ".join(report.errors)
            if source_columns == {"id", "date", "store", "item"} and "units_sold" not in frame:
                message = (
                    "This CSV has no historical sales. For Kaggle Store Item data, upload "
                    "train.csv (date, store, item, sales). test.csv only lists rows to forecast."
                )
            elif source_columns == {"id", "sales"} and "date" not in frame:
                message = (
                    "This CSV has only IDs and sales values, without dated sales history. "
                    "For Kaggle Store Item data, upload train.csv. sample_submission.csv "
                    "is an output template, not training data."
                )
            raise AppError(message, details=report.model_dump())
    dataset = Dataset(
        id=str(uuid4()),
        filename=filename[:255],
        is_demo=is_demo,
        report=report.model_dump(),
        timings=timings,
    )
    storage.mkdir(parents=True, exist_ok=True)
    path = storage / f"{dataset.id}.csv"
    cleaned.to_csv(path, index=False, date_format="%Y-%m-%d")
    try:
        session.add(dataset)
        session.commit()
    except Exception:
        session.rollback()
        path.unlink(missing_ok=True)
        raise
    return dataset


def get_dataset(dataset_id: str, session: Session) -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise AppError("Dataset not found. Load the demo or upload a CSV first.", 404)
    return dataset


def load_dataset(dataset_id: str, session: Session, storage: Path) -> pd.DataFrame:
    dataset = get_dataset(dataset_id, session)
    path = storage / f"{dataset.id}.csv"
    if not path.is_file():
        raise AppError("Stored dataset file is unavailable. Please upload it again.", 409)
    with timed("dataset_load_seconds", {}):
        frame = pd.read_csv(
            path,
            parse_dates=["date"],
            dtype={
                "store_id": "string",
                "product_id": "string",
                "category": "string",
                "region": "string",
            },
        )
        frame.attrs.update(
            external_features=dataset.report.get("external_features", []),
            frequency=dataset.report.get("frequency", "auto"),
        )
        return frame
