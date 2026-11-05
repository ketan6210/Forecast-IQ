from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.data.repository import load_dataset
from backend.app.db.models import ForecastRun
from backend.app.db.session import get_session
from backend.app.errors import AppError
from backend.app.forecasting.predictor import forecast_series
from backend.app.schemas.forecast import ForecastRequest, ForecastResponse

router = APIRouter(tags=["forecast"])


@router.post("/forecast", response_model=ForecastResponse)
def generate_forecast(
    body: ForecastRequest, request: Request, session: Session = Depends(get_session)
) -> ForecastResponse:
    frame = load_dataset(body.dataset_id, session, request.app.state.storage)
    result = forecast_series(frame, body)
    session.add(
        ForecastRun(
            id=result.run_id,
            dataset_id=body.dataset_id,
            selected_model=result.model,
            request=body.model_dump(),
            validation_metrics=result.validation_metrics.model_dump(),
            test_metrics=result.test_metrics.model_dump(),
            result=result.model_dump(),
        )
    )
    session.commit()
    return result


@router.get("/forecasts/{run_id}", response_model=ForecastResponse)
def forecast_detail(run_id: str, session: Session = Depends(get_session)) -> ForecastResponse:
    run = session.get(ForecastRun, run_id)
    if run is None:
        raise AppError("Forecast run not found.", 404)
    return ForecastResponse.model_validate(run.result)
