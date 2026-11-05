from typing import Literal

from pydantic import BaseModel, Field

ModelName = Literal["naive", "seasonal_naive", "moving_average", "linear_regression"]


class ForecastRequest(BaseModel):
    dataset_id: str = Field(min_length=1)
    store_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    horizon: Literal[7, 14, 28] = 28
    missing_policy: Literal["flag", "zero"] = "flag"


class Metrics(BaseModel):
    mae: float | None
    rmse: float | None
    wape: float | None
    smape: float | None
    mase: float | None


class ForecastPoint(BaseModel):
    date: str
    predicted_units: float


class HistoryPoint(BaseModel):
    date: str
    actual: float


class ModelComparison(BaseModel):
    model: ModelName
    validation_metrics: Metrics
    test_metrics: Metrics


class ForecastResponse(BaseModel):
    run_id: str
    dataset_id: str
    store_id: str
    product_id: str
    horizon: int
    missing_policy: Literal["flag", "zero"] = "flag"
    model: ModelName
    forecast: list[ForecastPoint]
    history: list[HistoryPoint]
    metrics: Metrics
    validation_metrics: Metrics
    test_metrics: Metrics
    comparison: list[ModelComparison]
    split: dict[str, dict[str, str | int]]
    summary: dict[str, float | None]
    timings: dict[str, float]
    warnings: list[str]
    assumptions: list[str]
    selection_reason: str
