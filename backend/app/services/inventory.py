"""Persisted inventory decisions; never calls forecast training or reads model artifacts."""

from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models import AdvancedRun, InventoryPlan, InventorySimulation
from backend.app.errors import AppError
from backend.app.inventory.analytics import portfolio, segment
from backend.app.inventory.recommendations import recommend
from backend.app.schemas.inventory import InventoryInputs, OptimizeRequest


def load_forecast(session: Session, run_id: str) -> dict:
    # Project only inventory inputs: large SHAP/model-comparison payloads stay in the DB.
    fields = ["store_id", "product_id", "frequency", "forecast", "history", "calibration"]
    row = session.execute(
        select(
            AdvancedRun.dataset_id, *[AdvancedRun.result[field].label(field) for field in fields]
        ).where(AdvancedRun.id == run_id)
    ).first()
    if row is None:
        raise AppError("Saved Phase 2 forecast not found. Train or select a forecast first.", 404)
    return {"run_id": run_id, **dict(row._mapping)}


def create_plan(session: Session, body: OptimizeRequest, cache: dict | None = None) -> dict:
    started = perf_counter()
    cache = cache if cache is not None else {}
    if body.forecast_run_id not in cache:
        cache[body.forecast_run_id] = load_forecast(session, body.forecast_run_id)
    inputs = InventoryInputs.model_validate(body.model_dump(exclude={"forecast_run_id"}))
    result = recommend(cache[body.forecast_run_id], inputs)
    plan_id = str(uuid4())
    now = datetime.now(timezone.utc)
    result.update(
        plan_id=plan_id,
        created_at=now.isoformat(),
        inputs=inputs.model_dump(),
        duration_seconds=perf_counter() - started,
    )
    session.add(
        InventoryPlan(
            id=plan_id,
            dataset_id=result["dataset_id"],
            forecast_run_id=body.forecast_run_id,
            sku_id=result["sku_id"],
            store_id=result["store_id"],
            location_id=result["location_id"],
            created_at=now,
            inputs=inputs.model_dump(),
            result=result,
        )
    )
    return result


def get_plan(session: Session, plan_id: str) -> InventoryPlan:
    plan = session.get(InventoryPlan, plan_id)
    if plan is None:
        raise AppError("Inventory plan not found.", 404)
    return plan


def latest_plans(dataset_id: str):
    ranked = (
        select(
            InventoryPlan.id,
            func.row_number()
            .over(
                partition_by=[
                    InventoryPlan.dataset_id,
                    InventoryPlan.store_id,
                    InventoryPlan.sku_id,
                    InventoryPlan.location_id,
                ],
                order_by=[InventoryPlan.created_at.desc(), InventoryPlan.id.desc()],
            )
            .label("rank"),
        )
        .where(InventoryPlan.dataset_id == dataset_id)
        .subquery()
    )
    return (
        select(InventoryPlan)
        .join(ranked, InventoryPlan.id == ranked.c.id)
        .where(ranked.c.rank == 1)
    )


def save_analysis(
    session: Session, plan_id: str, kind: str, configuration: dict, result: dict
) -> dict:
    now = datetime.now(timezone.utc)
    result = {
        **result,
        "analysis_id": str(uuid4()),
        "plan_id": plan_id,
        "created_at": now.isoformat(),
    }
    session.add(
        InventorySimulation(
            id=result["analysis_id"],
            plan_id=plan_id,
            kind=kind,
            created_at=now,
            configuration=configuration,
            result=result,
        )
    )
    session.commit()
    return result


def latest_analysis(session: Session, plan_id: str, kind: str) -> dict | None:
    return session.scalar(
        select(InventorySimulation.result)
        .where(InventorySimulation.plan_id == plan_id, InventorySimulation.kind == kind)
        .order_by(InventorySimulation.created_at.desc(), InventorySimulation.id.desc())
        .limit(1)
    )


def portfolio_records(session: Session, dataset_id: str) -> list[dict]:
    # Only compact KPI/segmentation fields cross the DB boundary, streamed in chunks.
    fields = [
        "sku_id",
        "store_id",
        "location_id",
        "risk_level",
        "reorder_needed",
        "currency",
        "inventory_value",
        "recommended_order_quantity",
        "service_level",
        "annual_demand",
        "unit_cost",
        "historical_mean",
        "historical_std",
        "frequency",
        "forecast_start",
        "expedite_needed",
    ]
    query = latest_plans(dataset_id).with_only_columns(
        InventoryPlan.id.label("plan_id"), *[InventoryPlan.result[k].label(k) for k in fields]
    )
    return [dict(row._mapping) for row in session.execute(query).yield_per(200)]


def portfolio_kpis(session: Session, dataset_id: str) -> dict:
    rows = portfolio_records(session, dataset_id)
    summary = portfolio(rows)
    summary["abc_distribution"] = segment(rows)["abc_distribution"]
    metrics = [
        "expected_holding_cost",
        "expected_stockout_cost",
        "expected_ordering_cost",
        "expected_total_cost",
        "fill_rate",
        "average_service_level",
        "horizon",
        "mode",
        "shortage_mode",
    ]
    ranked = (
        select(
            InventorySimulation.id,
            func.row_number()
            .over(
                partition_by=InventorySimulation.plan_id,
                order_by=[InventorySimulation.created_at.desc(), InventorySimulation.id.desc()],
            )
            .label("rank"),
        )
        .where(InventorySimulation.kind == "simulation")
        .subquery()
    )
    plans = latest_plans(dataset_id).with_only_columns(InventoryPlan.id).subquery()
    query = (
        select(
            InventorySimulation.plan_id, *[InventorySimulation.result[k].label(k) for k in metrics]
        )
        .join(ranked, ranked.c.id == InventorySimulation.id)
        .join(plans, plans.c.id == InventorySimulation.plan_id)
        .where(ranked.c.rank == 1)
    )
    simulations = {r.plan_id: dict(r._mapping) for r in session.execute(query).yield_per(200)}
    comparable = (
        bool(rows)
        and len(simulations) == len(rows)
        and len(
            {
                (
                    r["frequency"],
                    r["forecast_start"],
                    simulations.get(r["plan_id"], {}).get("horizon"),
                    simulations.get(r["plan_id"], {}).get("mode"),
                    simulations.get(r["plan_id"], {}).get("shortage_mode"),
                )
                for r in rows
            }
        )
        == 1
    )
    monetary = comparable and len({r["currency"] for r in rows}) == 1
    summary["simulated_series_count"] = len(simulations)
    for key in metrics[:6]:
        values = [s[key] for s in simulations.values()]
        complete = (monetary if key.startswith("expected_") else comparable) and all(
            value is not None for value in values
        )
        summary[key] = (
            (sum(values) / len(values) if key in metrics[4:6] else sum(values))
            if complete
            else None
        )
    summary["notes"].append(
        "Simulated totals require every current plan to have a simulation "
        "with matching forecast start, frequency, horizon, simulation and shortage modes; "
        "monetary sums also "
        "require a shared currency. Service means weight series equally. "
        "Portfolio cost percentiles are not inferred from marginal results."
    )
    return summary
