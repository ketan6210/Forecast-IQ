import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api import advanced, allocation, analytics, datasets, forecast, inventory
from backend.app.config import settings
from backend.app.db.migrations import migrate_database
from backend.app.db.session import build_session_factory
from backend.app.errors import AppError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def create_app(database_url: str | None = None, storage_dir: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.storage.mkdir(parents=True, exist_ok=True)
        migrate_database(app.state.session_factory.kw["bind"])
        yield
        app.state.session_factory.kw["bind"].dispose()

    app = FastAPI(title="ForecastIQ", version="3.0.0", lifespan=lifespan)
    app.state.storage = storage_dir or settings.storage_dir
    app.state.session_factory = build_session_factory(database_url or settings.database_url)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins.split(","),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(AppError)
    async def domain_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"error": exc.message, "details": exc.details}
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]} for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": "Invalid request. Check the indicated fields.", "details": fields},
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("Database operation failed", exc_info=exc)
        return JSONResponse(
            status_code=503, content={"error": "Database unavailable. Please retry shortly."}
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unexpected request failure", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"error": "The request could not be completed. Check server logs or retry."},
        )

    @app.get("/health", tags=["health"])
    def health() -> dict:
        with app.state.session_factory() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok", "phase": 3}

    app.include_router(datasets.router)
    app.include_router(analytics.router)
    app.include_router(forecast.router)
    app.include_router(advanced.router)
    app.include_router(inventory.router)
    app.include_router(allocation.router)
    return app


app = create_app()
