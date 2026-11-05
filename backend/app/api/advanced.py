import csv
import io
import shutil
import threading
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.data.frequency import future_dates
from backend.app.data.repository import load_dataset
from backend.app.db.models import AdvancedRun
from backend.app.db.session import get_session
from backend.app.errors import AppError
from backend.app.models.base import checked
from backend.app.schemas.advanced import PredictRequest, SeriesComparisonRequest, TrainingRequest
from backend.app.services.advanced_training import quantile_points, train_advanced
from backend.app.services.artifacts import load_artifact

router = APIRouter(prefix="/forecast", tags=["advanced forecasting"])
training_slot = threading.BoundedSemaphore(1)


def get_run(run_id: str, session: Session) -> AdvancedRun:
    run = session.get(AdvancedRun, run_id)
    if run is None:
        raise AppError("Training run not found.", 404)
    return run


@router.post("/train", status_code=201)
def train(body: TrainingRequest, request: Request, session: Session = Depends(get_session)) -> dict:
    if not training_slot.acquire(blocking=False):
        raise AppError(
            "Another advanced training run is active. Please retry when it finishes.", 409
        )
    run_id = str(uuid4())
    directory = request.app.state.storage / "artifacts" / run_id
    try:
        frame = load_dataset(body.dataset_id, session, request.app.state.storage)
        result = train_advanced(frame, body, run_id, directory)
        session.add(
            AdvancedRun(
                id=run_id,
                dataset_id=body.dataset_id,
                champion_model=result["champion_model"],
                configuration=body.model_dump(),
                result=result,
            )
        )
        session.commit()
        return result
    except Exception:
        session.rollback()
        if directory.exists():
            shutil.rmtree(directory)
        raise
    finally:
        training_slot.release()


@router.get("/runs/{run_id}")
def run_detail(run_id: str, session: Session = Depends(get_session)) -> dict:
    return get_run(run_id, session).result


@router.get("/models")
def models(
    dataset_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[dict]:
    query = select(
        AdvancedRun.id,
        AdvancedRun.champion_model,
        AdvancedRun.created_at,
        AdvancedRun.configuration,
        AdvancedRun.result["artifacts"].label("artifacts"),
        AdvancedRun.result["test_metrics"].label("test_metrics"),
    )
    if dataset_id:
        query = query.where(AdvancedRun.dataset_id == dataset_id)
    query = (
        query.order_by(AdvancedRun.created_at.desc(), AdvancedRun.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [
        {
            "run_id": row.id,
            "champion_model": row.champion_model,
            "created_at": row.created_at.isoformat(),
            "configuration": row.configuration,
            "models": list(row.artifacts),
            "test_metrics": row.test_metrics,
        }
        for row in session.execute(query)
    ]


@router.get("/model-comparison")
def comparison(run_id: str, session: Session = Depends(get_session)) -> list[dict]:
    return get_run(run_id, session).result["comparison"]


@router.get("/backtest")
def backtest(
    run_id: str, model: str | None = None, session: Session = Depends(get_session)
) -> dict:
    result = get_run(run_id, session).result
    name = model or result["champion_model"]
    row = next(
        (r for r in result["comparison"] if r["model"] == name and r["status"] == "ok"), None
    )
    if row is None:
        raise AppError("No successful backtest for that model.", 404)
    return {"model": name, "folds": row["folds"], "summary": row["summary"]}


@router.get("/explainability")
def explainability(
    run_id: str, model: str = "lightgbm", session: Session = Depends(get_session)
) -> dict:
    result = get_run(run_id, session).result
    if model not in result["explainability"]:
        raise AppError(
            "SHAP is available for successfully trained LightGBM/XGBoost candidates only.", 404
        )
    return result["explainability"][model]


@router.post("/predict")
def predict(
    body: PredictRequest, request: Request, session: Session = Depends(get_session)
) -> dict:
    run = get_run(body.run_id, session)
    result = run.result
    horizon = body.horizon or result["forecast_horizon"]
    if horizon > result["forecast_horizon"]:
        raise AppError(
            "Retrain with the longer horizon to evaluate and calibrate those forecast leads."
        )
    directory = request.app.state.storage / "artifacts" / run.id
    model = load_artifact(directory, run.champion_model)
    calibrator = load_artifact(directory, "calibrator")
    quantiles = calibrator.predict(checked(model, horizon))
    dates = future_dates(pd.Timestamp(result["history"][-1]["date"]), horizon, result["frequency"])
    return {
        "run_id": run.id,
        "champion_model": run.champion_model,
        "forecast_horizon": horizon,
        "frequency": result["frequency"],
        "forecast": quantile_points(dates, quantiles),
        "evaluation_metrics": result["test_metrics"],
        "probabilistic_metrics": result["probabilistic_metrics"],
    }


@router.get("/export/{run_id}")
def export(run_id: str, session: Session = Depends(get_session)) -> Response:
    result = get_run(run_id, session).result
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["date", "p10", "p50", "p90"])
    writer.writeheader()
    writer.writerows(result["forecast"])
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="forecast-{run_id}.csv"'},
    )


@router.post("/series-comparison")
def compare_series(body: SeriesComparisonRequest, session: Session = Depends(get_session)) -> dict:
    comparison = []
    for series in body.series:
        fields = [
            "frequency",
            "forecast_horizon",
            "partitions",
            "test_metrics",
            "probabilistic_metrics",
            "forecast",
        ]
        run = session.execute(
            select(
                AdvancedRun.id,
                AdvancedRun.champion_model,
                *[AdvancedRun.result[k].label(k) for k in fields],
            )
            .where(
                AdvancedRun.dataset_id == body.dataset_id,
                AdvancedRun.configuration["store_id"].as_string() == series.store_id,
                AdvancedRun.configuration["product_id"].as_string() == series.product_id,
            )
            .order_by(AdvancedRun.created_at.desc(), AdvancedRun.id.desc())
            .limit(1)
        ).first()
        if run is None:
            comparison.append({**series.model_dump(), "status": "not_trained"})
        else:
            result = dict(run._mapping)
            comparison.append(
                {
                    **series.model_dump(),
                    "status": "ok",
                    "run_id": run.id,
                    "champion_model": run.champion_model,
                    "frequency": result["frequency"],
                    "horizon": result["forecast_horizon"],
                    "test_period": result["partitions"]["test"],
                    "test_metrics": result["test_metrics"],
                    "probabilistic_metrics": result["probabilistic_metrics"],
                    "median_total": sum(p["p50"] for p in result["forecast"]),
                }
            )
    return {
        "series": comparison,
        "note": "Independent series; compare metrics in context of their horizons, "
        "test dates and demand scales.",
    }
