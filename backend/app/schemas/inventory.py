"""Explicit inventory assumptions; absent business costs remain unknown."""

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class Arrival(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    period: int = Field(ge=1, le=730)
    quantity: float = Field(gt=0)


class InventoryInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, populate_by_name=True)

    on_hand_inventory: float = Field(
        ge=0, validation_alias=AliasChoices("on_hand_inventory", "current_inventory")
    )
    on_order_inventory: float = Field(default=0, ge=0)
    backorders: float = Field(default=0, ge=0)
    lead_time: int = Field(ge=0, le=365)
    lead_time_std: float = Field(default=0, ge=0, le=365)
    service_level: float = Field(default=0.95, ge=0.5, lt=1)
    safety_stock_method: Literal["none", "demand", "demand_lead_time", "quantile"] = "quantile"
    demand_std: float | None = Field(default=None, ge=0)
    unit_cost: float | None = Field(default=None, ge=0)
    selling_price: float | None = Field(default=None, ge=0)
    holding_cost_per_unit_per_year: float | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("holding_cost_per_unit_per_year", "holding_cost_per_unit"),
    )
    annual_holding_rate: float | None = Field(default=None, ge=0)
    stockout_cost: float | None = Field(default=None, ge=0)
    ordering_cost: float | None = Field(default=None, ge=0)
    annual_demand: float | None = Field(default=None, ge=0)
    annualize_forecast: bool = False
    minimum_order_quantity: float = Field(default=0, ge=0)
    order_multiple: float = Field(default=1, gt=0)
    target_coverage_periods: int | None = Field(default=None, ge=1, le=90)
    max_inventory_position: float | None = Field(default=None, ge=0)
    incoming_orders: list[Arrival] = Field(default_factory=list, max_length=100)
    warehouse_id: str | None = Field(default=None, min_length=1, max_length=100)
    supplier_id: str | None = Field(default=None, min_length=1, max_length=100)
    currency: str | None = Field(default=None, min_length=1, max_length=30)
    cogs_for_horizon: float | None = Field(default=None, ge=0)
    sampling_method: Literal["residual_bootstrap", "quantile_interpolation"] = "residual_bootstrap"
    block_size: int = Field(default=1, ge=1, le=30)
    uncertainty_samples: int = Field(default=1000, ge=100, le=10000)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def consistent_inputs(self):
        if self.lead_time == 0 and self.lead_time_std > 0:
            raise ValueError("Zero mean lead time cannot have positive lead-time variability.")
        if self.safety_stock_method == "demand" and self.lead_time_std > 0:
            raise ValueError("Fixed-lead demand safety stock requires lead_time_std=0.")
        if self.annual_holding_rate is not None:
            if self.holding_cost_per_unit_per_year is not None:
                raise ValueError("Choose a direct annual holding cost or a rate, not both.")
            if self.unit_cost is None:
                raise ValueError("An annual holding rate requires unit_cost.")
        if self.annual_demand is not None and self.annualize_forecast:
            raise ValueError("Supply annual demand or request forecast annualization, not both.")
        if self.incoming_orders:
            total = sum(item.quantity for item in self.incoming_orders)
            if abs(total - self.on_order_inventory) > 1e-6 * max(1, total):
                raise ValueError("Incoming order quantities must sum to on_order_inventory.")
        return self


class OptimizeRequest(InventoryInputs):
    forecast_run_id: str = Field(min_length=1, max_length=36)


class BatchRequest(BaseModel):
    items: list[OptimizeRequest] = Field(min_length=1, max_length=1000)


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    plan_id: str
    mode: Literal["deterministic", "monte_carlo"] = "monte_carlo"
    horizon: int | None = Field(default=None, ge=1, le=90)
    trials: int = Field(default=500, ge=100, le=1000)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    shortage_mode: Literal["lost_sales", "backorders"] = "lost_sales"


class PolicyRequest(SimulationRequest):
    minimum_fill_rate: float = Field(default=0.95, ge=0, le=1)
    service_levels: list[float] = Field(
        default_factory=lambda: [0.9, 0.95, 0.975, 0.99], min_length=1, max_length=8
    )

    @model_validator(mode="after")
    def valid_levels(self):
        if any(not 0.5 <= value < 1 for value in self.service_levels):
            raise ValueError("Candidate service levels must be at least 0.5 and less than 1.")
        self.service_levels = sorted(set(self.service_levels))
        self.mode = "monte_carlo"
        return self


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str
    changes: dict
    horizon: int | None = Field(default=None, ge=1, le=90)
    trials: int = Field(default=500, ge=100, le=1000)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    shortage_mode: Literal["lost_sales", "backorders"] = "lost_sales"


class SegmentationRequest(BaseModel):
    dataset_id: str
    a_threshold: float = Field(default=0.8, gt=0, lt=1)
    b_threshold: float = Field(default=0.95, gt=0, le=1)
    x_threshold: float = Field(default=0.5, ge=0)
    y_threshold: float = Field(default=1.0, gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.a_threshold >= self.b_threshold or self.x_threshold >= self.y_threshold:
            raise ValueError("ABC and XYZ thresholds must be strictly ordered.")
        return self
