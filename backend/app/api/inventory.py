import csv
import io
import json
from time import perf_counter

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.app.db.models import InventoryPlan
from backend.app.db.session import get_session
from backend.app.errors import AppError
from backend.app.inventory.analytics import portfolio, segment
from backend.app.inventory.policies import compare_policies
from backend.app.inventory.recommendations import recommend
from backend.app.schemas.inventory import (
    BatchRequest,
    InventoryInputs,
    OptimizeRequest,
    PolicyRequest,
    ScenarioRequest,
    SegmentationRequest,
    SimulationRequest,
)
from backend.app.services.inventory import (
    create_plan,
    get_plan,
    latest_analysis,
    latest_plans,
    load_forecast,
    portfolio_kpis,
    portfolio_records,
    save_analysis,
)
from backend.app.simulation.inventory_simulator import run_simulation

router = APIRouter(prefix="/inventory", tags=["inventory optimization"])


@router.post("/optimize", status_code=201)
def optimize(body: OptimizeRequest, session: Session = Depends(get_session)) -> dict:
    result = create_plan(session, body)
    session.commit()
    return result


def batch_items(items: list[dict | OptimizeRequest], session: Session) -> dict:
    started = perf_counter()
    cache, results, errors = {}, [], []
    for index, item in enumerate(items):
        try:
            body = (
                item if isinstance(item, OptimizeRequest) else OptimizeRequest.model_validate(item)
            )
            results.append(create_plan(session, body, cache))
        except (AppError, ValidationError) as exc:
            errors.append({"row": index + 1, "error": str(exc)})
    session.commit()
    return {
        "items": results,
        "errors": errors,
        "successful": len(results),
        "failed": len(errors),
        "portfolio": portfolio(results),
        "duration_seconds": perf_counter() - started,
    }


@router.post("/batch", status_code=201)
def batch(body: BatchRequest, session: Session = Depends(get_session)) -> dict:
    return batch_items(body.items, session)


@router.post("/import", status_code=201)
def import_csv(file: UploadFile = File(...), session: Session = Depends(get_session)) -> dict:
    data = file.file.read(2_000_001)
    if len(data) > 2_000_000:
        raise AppError("Inventory CSV must be at most 2 MB.", 413)
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        if not reader.fieldnames or not {"forecast_run_id", "lead_time"}.issubset(
            reader.fieldnames
        ):
            raise AppError("CSV requires forecast_run_id, on_hand_inventory and lead_time columns.")
        items = []
        for row in reader:
            if len(items) >= 1000:
                raise AppError("Import at most 1,000 inventory rows per batch.")
            cleaned = {
                k: v.strip() for k, v in row.items() if k and isinstance(v, str) and v.strip()
            }
            if row.get(None):
                raise AppError("CSV has extra columns. Quote JSON arrival schedules correctly.")
            if "incoming_orders" in cleaned:
                cleaned["incoming_orders"] = json.loads(cleaned["incoming_orders"])
            items.append(cleaned)
    except (UnicodeDecodeError, csv.Error, json.JSONDecodeError) as exc:
        raise AppError(
            "Upload UTF-8 CSV; incoming_orders must contain a valid JSON array."
        ) from exc
    if not items:
        raise AppError("Inventory CSV contains no rows.")
    return batch_items(items, session)


@router.get("/recommendations")
def recommendations(
    dataset_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    risk: str | None = None,
    reorder_only: bool = False,
    search: str = "",
    sort: str = "priority",
    session: Session = Depends(get_session),
) -> dict:
    query = latest_plans(dataset_id)
    if risk:
        if risk not in {"low", "medium", "high"}:
            raise AppError("Risk must be low, medium or high.")
        query = query.where(InventoryPlan.result["risk_level"].as_string() == risk)
    if reorder_only:
        query = query.where(InventoryPlan.result["reorder_needed"].as_boolean().is_(True))
    if search:
        query = query.where(
            InventoryPlan.sku_id.contains(search, autoescape=True)
            | InventoryPlan.location_id.contains(search, autoescape=True)
        )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    risk_order = case(
        (InventoryPlan.result["risk_level"].as_string() == "high", 0),
        (InventoryPlan.result["risk_level"].as_string() == "medium", 1),
        else_=2,
    )
    sorts = {
        "priority": [
            risk_order,
            InventoryPlan.result["expedite_quantity"].as_float().desc().nulls_last(),
            InventoryPlan.result["units_below_reorder_point"].as_float().desc(),
            InventoryPlan.result["forecast_p50_total"].as_float().desc(),
        ],
        "sku": [InventoryPlan.sku_id],
        "quantity": [InventoryPlan.result["recommended_order_quantity"].as_float().desc()],
    }
    if sort not in sorts:
        raise AppError("Sort must be priority, sku or quantity.")
    rows = session.scalars(
        query.order_by(*sorts[sort], InventoryPlan.id).offset(offset).limit(limit)
    )
    return {
        "items": [r.result for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "note": "Latest plan per dataset/store/SKU/location. Older plans remain available by ID.",
    }


@router.get("/plans/{plan_id}")
def plan_detail(plan_id: str, session: Session = Depends(get_session)) -> dict:
    plan = get_plan(session, plan_id)
    return {
        **plan.result,
        "latest_simulation": latest_analysis(session, plan_id, "simulation"),
        "latest_comparison": latest_analysis(session, plan_id, "policy_comparison"),
    }


@router.get("/sku/{sku_id}")
def sku_detail(sku_id: str, dataset_id: str, session: Session = Depends(get_session)) -> dict:
    rows = session.scalars(latest_plans(dataset_id).where(InventoryPlan.sku_id == sku_id))
    return {"sku_id": sku_id, "items": [r.result for r in rows]}


@router.post("/simulate", status_code=201)
def simulate(body: SimulationRequest, session: Session = Depends(get_session)) -> dict:
    plan = get_plan(session, body.plan_id)
    result = run_simulation(
        load_forecast(session, plan.forecast_run_id),
        InventoryInputs.model_validate(plan.inputs),
        plan.result,
        body,
    )
    return save_analysis(session, plan.id, "simulation", body.model_dump(), result)


@router.post("/policy-comparison", status_code=201)
def policy_comparison(body: PolicyRequest, session: Session = Depends(get_session)) -> dict:
    plan = get_plan(session, body.plan_id)
    result = compare_policies(
        load_forecast(session, plan.forecast_run_id),
        InventoryInputs.model_validate(plan.inputs),
        body,
    )
    return save_analysis(session, plan.id, "policy_comparison", body.model_dump(), result)


@router.get("/policy-comparison")
def saved_comparison(plan_id: str, session: Session = Depends(get_session)) -> dict:
    get_plan(session, plan_id)
    result = latest_analysis(session, plan_id, "policy_comparison")
    if result is None:
        raise AppError("No policy comparison has been run for this plan.", 404)
    return result


@router.post("/scenario", status_code=201)
def scenario(body: ScenarioRequest, session: Session = Depends(get_session)) -> dict:
    plan = get_plan(session, body.plan_id)
    try:
        inputs = InventoryInputs.model_validate({**plan.inputs, **body.changes})
    except ValidationError as exc:
        raise AppError(str(exc), 422) from exc
    forecast = load_forecast(session, plan.forecast_run_id)
    if body.horizon is not None:
        if body.horizon > len(forecast["forecast"]):
            raise AppError("What-if horizon exceeds the saved forecast. Train a longer forecast.")
        forecast = {**forecast, "forecast": forecast["forecast"][: body.horizon]}
    baseline_inputs = InventoryInputs.model_validate(plan.inputs)
    baseline = {**recommend(forecast, baseline_inputs), "inputs": plan.inputs}
    changed = recommend(forecast, inputs)
    changed["inputs"] = inputs.model_dump()
    request = SimulationRequest(
        plan_id=plan.id,
        horizon=body.horizon,
        trials=body.trials,
        seed=body.seed,
        shortage_mode=body.shortage_mode,
    )
    base_sim = run_simulation(forecast, baseline_inputs, baseline, request)
    changed_sim = run_simulation(forecast, inputs, changed, request)
    return save_analysis(
        session,
        plan.id,
        "scenario",
        body.model_dump(),
        {
            "baseline": {"recommendation": baseline, "simulation": base_sim},
            "scenario": {"recommendation": changed, "simulation": changed_sim},
            "changes": body.changes,
            "forecast_run_id": plan.forecast_run_id,
            "note": (
                "Both input sets are recalculated over the requested forecast horizon using "
                "the same saved forecast and simulation seed; no retraining. "
                "The saved plan is unchanged."
            ),
        },
    )


@router.get("/kpis")
def kpis(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    return portfolio_kpis(session, dataset_id)


@router.post("/abc-analysis")
def abc(body: SegmentationRequest, session: Session = Depends(get_session)) -> dict:
    return segment(
        portfolio_records(session, body.dataset_id),
        body.a_threshold,
        body.b_threshold,
        body.x_threshold,
        body.y_threshold,
    )


@router.get("/abc-analysis")
def abc_default(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    return abc(SegmentationRequest(dataset_id=dataset_id), session)


@router.get("/export")
def export(dataset_id: str, session: Session = Depends(get_session)) -> Response:
    columns = [
        "sku_id",
        "store_id",
        "location_id",
        "forecast_run_id",
        "plan_id",
        "forecast_horizon",
        "frequency",
        "p50_lead_time_demand",
        "p90_lead_time_demand",
        "on_hand_inventory",
        "inventory_position",
        "safety_stock",
        "reorder_point",
        "eoq",
        "recommended_order_quantity",
        "reorder_needed",
        "stockout_risk",
        "expedite_needed",
        "expedite_quantity",
        "supply_schedule_status",
        "service_level",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    query = latest_plans(dataset_id).with_only_columns(
        *[InventoryPlan.result[k].label(k) for k in columns]
    )
    for row in session.execute(query).yield_per(200):
        values = dict(row._mapping)
        # Spreadsheet formula injection: exported identifiers remain literal strings.
        writer.writerow(
            {
                key: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v
                for key, v in values.items()
            }
        )
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="inventory-recommendations.csv"'},
    )
