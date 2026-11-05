import hashlib
import json
from pathlib import Path

import joblib

from backend.app.errors import AppError


def save_artifact(directory: Path, name: str, model, metadata: dict) -> dict:
    """Write only server-generated artifacts and an integrity manifest in an owned run directory."""
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{name}.joblib"
    joblib.dump(model, destination, compress=3)
    manifest = {
        **metadata,
        "file": destination.name,
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    }
    (directory / f"{name}.json").write_text(json.dumps(manifest, indent=2, allow_nan=False))
    return manifest


def load_artifact(directory: Path, name: str):
    """Never accept paths or serialized objects from clients; verify the local manifest first."""
    if name not in {
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
        "calibrator",
    }:
        raise AppError("Unknown model artifact.", 404)
    path = directory / f"{name}.joblib"
    metadata = directory / f"{name}.json"
    if not path.is_file() or not metadata.is_file():
        raise AppError("Model artifact is unavailable. Train a new run.", 409)
    try:
        manifest = json.loads(metadata.read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"]:
            raise AppError("Artifact integrity check failed. Train a new run.", 409)
        return joblib.load(path)
    except AppError:
        raise
    except Exception as exc:
        raise AppError("Saved model cannot be loaded with this runtime. Retrain it.", 409) from exc
