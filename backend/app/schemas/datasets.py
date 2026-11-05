from typing import Literal

from pydantic import BaseModel, Field


class ValidationReport(BaseModel):
    frequency: str = "D"
    column_mapping: dict[str, str] = Field(default_factory=dict)
    external_features: list[str] = Field(default_factory=list)
    row_count: int
    processed_row_count: int = 0
    date_min: str | None = None
    date_max: str | None = None
    store_count: int = 0
    product_count: int = 0
    category_count: int | None = None
    missing_value_summary: dict[str, int] = Field(default_factory=dict)
    missing_rate: float = 0
    duplicate_count: int = 0
    duplicate_observation_count: int = 0
    invalid_date_count: int = 0
    negative_sales_count: int = 0
    invalid_price_count: int = 0
    missing_date_count: int = 0
    chronologically_ordered: bool = True
    validation_status: Literal["PASS", "PASS_WITH_WARNINGS", "FAIL"] = "PASS"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class DatasetResponse(ValidationReport):
    dataset_id: str
    filename: str
    is_demo: bool
    created_at: str
    timings: dict[str, float]


class DatasetOptions(BaseModel):
    frequency: str = "D"
    stores: list[str]
    products: list[str]
    categories: list[str]
    store_products: dict[str, list[str]]
    date_min: str
    date_max: str
