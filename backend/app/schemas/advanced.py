from typing import Literal

from pydantic import BaseModel, Field, model_validator

AdvancedModel = Literal[
    "naive",
    "seasonal_naive",
    "moving_average",
    "linear_regression",
    "arima",
    "sarima",
    "ets",
    "lightgbm",
    "xgboost",
    "nbeats",
]


class TrainingRequest(BaseModel):
    dataset_id: str = Field(min_length=1)
    store_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    horizon: int = Field(default=28, ge=1, le=90)
    folds: int = Field(default=3, ge=2, le=5)
    window: Literal["expanding", "rolling"] = "expanding"
    window_size: int = Field(default=180, ge=60, le=5000)
    frequency: Literal["auto", "daily", "weekly", "monthly"] = "auto"
    missing_policy: Literal["flag", "zero"] = "flag"
    models: list[AdvancedModel] = Field(
        default_factory=lambda: [
            "naive",
            "seasonal_naive",
            "moving_average",
            "linear_regression",
            "arima",
            "sarima",
            "ets",
            "lightgbm",
            "xgboost",
            "nbeats",
        ],
        min_length=1,
    )
    tune: bool = True
    tuning_trials: int = Field(default=4, ge=1, le=10)
    tuning_seed: int = Field(default=42, ge=0, le=2**32 - 1)
    neural_epochs: int = Field(default=12, ge=1, le=30)

    @model_validator(mode="after")
    def baseline_always_available(self) -> "TrainingRequest":
        self.models = list(
            dict.fromkeys(["naive", "seasonal_naive", "moving_average", *self.models])
        )
        return self


class PredictRequest(BaseModel):
    run_id: str
    horizon: int | None = Field(default=None, ge=1, le=90)


class SeriesSelection(BaseModel):
    store_id: str
    product_id: str


class SeriesComparisonRequest(BaseModel):
    dataset_id: str
    series: list[SeriesSelection] = Field(min_length=2, max_length=4)
