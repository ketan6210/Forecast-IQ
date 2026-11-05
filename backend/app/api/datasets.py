from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import ROOT, settings
from backend.app.data.repository import get_dataset, ingest, load_dataset, response_for
from backend.app.db.models import Dataset
from backend.app.db.session import get_session
from backend.app.errors import AppError
from backend.app.schemas.datasets import DatasetOptions, DatasetResponse

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetResponse])
def list_datasets(session: Session = Depends(get_session)) -> list[DatasetResponse]:
    rows = session.scalars(select(Dataset).order_by(Dataset.created_at.desc()).limit(100)).all()
    return [response_for(row) for row in rows]


@router.post("/upload", response_model=DatasetResponse, status_code=201)
def upload_dataset(
    file: UploadFile,
    request: Request,
    session: Session = Depends(get_session),
    frequency: str = Form("auto"),
    date_column: str = Form("date"),
    target_column: str = Form("units_sold"),
    store_column: str = Form("store_id"),
    product_column: str = Form("product_id"),
    price_column: str = Form("price"),
    external_features: str = Form(""),
) -> DatasetResponse:
    if not file.filename or Path(file.filename).suffix.lower() != ".csv":
        raise AppError("Upload a file with the .csv extension.", 415)
    if file.content_type not in {
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
        "application/octet-stream",
        "text/plain",
        None,
    }:
        raise AppError("Unsupported file type. Upload a CSV file.", 415)
    content = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(f"File exceeds the {settings.max_upload_mb} MB upload limit.", 413)
    return response_for(
        ingest(
            content,
            Path(file.filename).name,
            False,
            session,
            request.app.state.storage,
            frequency,
            {
                "date": date_column,
                "units_sold": target_column,
                "store_id": store_column,
                "product_id": product_column,
                "price": price_column,
            },
            [c.strip() for c in external_features.split(",") if c.strip()],
        )
    )


@router.post("/demo", response_model=DatasetResponse, status_code=201)
def load_demo(request: Request, session: Session = Depends(get_session)) -> DatasetResponse:
    path = ROOT / "data" / "demo" / "retail_sales.csv"
    return response_for(
        ingest(path.read_bytes(), "Synthetic retail demo", True, session, request.app.state.storage)
    )


@router.get("/{dataset_id}", response_model=DatasetResponse)
def dataset_detail(dataset_id: str, session: Session = Depends(get_session)) -> DatasetResponse:
    return response_for(get_dataset(dataset_id, session))


@router.get("/{dataset_id}/options", response_model=DatasetOptions)
def dataset_options(
    dataset_id: str, request: Request, session: Session = Depends(get_session)
) -> DatasetOptions:
    df = load_dataset(dataset_id, session, request.app.state.storage)
    return DatasetOptions(
        frequency=get_dataset(dataset_id, session).report.get("frequency", "D"),
        stores=sorted(df.store_id.unique()),
        products=sorted(df.product_id.unique()),
        categories=sorted(df.category.dropna().unique()) if "category" in df else [],
        store_products={
            str(store): sorted(group.product_id.unique()) for store, group in df.groupby("store_id")
        },
        date_min=df.date.min().date().isoformat(),
        date_max=df.date.max().date().isoformat(),
    )
