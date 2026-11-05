"""Register an operator-owned local forecast catalog without retraining or unpickling it.

Checksums detect damaged files; they do not make an untrusted pickle safe. This service is
deliberately available only to the local CLI, never to a client upload/path API.
"""

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from backend.app.data.frequency import future_dates, prepare_series, resolve_frequency
from backend.app.data.repository import load_dataset
from backend.app.db.models import AdvancedRun
from backend.app.errors import AppError
from backend.app.models.registry import FAMILIES
from backend.app.schemas.advanced import TrainingRequest


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_owned(root: Path, path: Path) -> bytes:
    if not path.resolve().is_relative_to(root):
        raise ValueError("Catalog files must stay inside the source directory.")
    return path.read_bytes()


def decode(content: bytes) -> dict:
    value = json.loads(content)
    # Reject NaN/Infinity anywhere in a checkpoint, including nested metrics.
    json.dumps(value, allow_nan=False)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return value


def validate_run(result: dict, groups, attributes: dict) -> str:
    request = TrainingRequest.model_validate(result["configuration"])
    for field in ("dataset_id", "store_id", "product_id"):
        if result[field] != getattr(request, field):
            raise ValueError(f"Checkpoint {field} disagrees with its configuration.")
    raw = groups.get_group((request.store_id, request.product_id)).copy()
    raw.attrs.update(attributes)
    declared = attributes.get("frequency", "auto")
    requested = (
        declared if request.frequency == "auto" and declared != "mixed" else request.frequency
    )
    frequency = resolve_frequency(raw.date, requested)
    series = prepare_series(raw, frequency, request.missing_policy)
    history = [
        {"date": row.date.date().isoformat(), "actual": float(row.units_sold)}
        for row in series.itertuples()
    ]
    if result["history"] != history:
        raise ValueError("Saved history does not match the selected dataset.")
    if result["frequency"] != frequency or result["forecast_horizon"] != request.horizon:
        raise ValueError("Frequency or horizon disagrees with the training configuration.")
    dates = [
        d.date().isoformat() for d in future_dates(series.date.iloc[-1], request.horizon, frequency)
    ]
    if [p["date"] for p in result["forecast"]] != dates:
        raise ValueError("Forecast dates do not continue the selected history.")
    quantiles = np.array([[p[k] for k in ("p10", "p50", "p90")] for p in result["forecast"]], float)
    if (
        not np.isfinite(quantiles).all()
        or (quantiles < 0).any()
        or (np.diff(quantiles, axis=1) < 0).any()
    ):
        raise ValueError("Invalid forecast quantiles.")
    calibration = result["calibration"]
    records = calibration["records"]
    if len(records) < 20 or calibration["residual_count"] != len(records):
        raise ValueError("Missing calibration residuals for inventory simulation.")
    actuals = {r["date"]: r["actual"] for r in history}
    for row in records:
        if (
            actuals.get(row["date"]) != row["actual"]
            or not row["training_end"] < row["date"] < result["partitions"]["test"]["start"]
            or not np.isclose(row["residual"], row["actual"] - row["predicted"])
        ):
            raise ValueError("Calibration residuals disagree with dated history.")
    if result["champion_model"] not in result["artifacts"]:
        raise ValueError("Missing champion artifact.")
    # Required by the existing saved-run, model comparison and dashboard endpoints.
    for key in ("test_metrics", "probabilistic_metrics", "comparison", "explainability"):
        if key not in result:
            raise ValueError(f"Missing saved-run field: {key}.")
    return digest(series.to_csv(index=False).encode())


def import_catalog(
    session: Session, storage: Path, source: Path, dataset_id: str, *, dry_run: bool = False
) -> dict:
    """Use a dedicated session. Commit all runs together; clean owned files on failure."""
    source = source.resolve()
    frame = load_dataset(dataset_id, session, storage)
    groups = frame.groupby(["store_id", "product_id"], sort=False)
    checkpoints = sorted((source / "runs").glob("*.json"))
    if not checkpoints:
        raise AppError("No runs/*.json checkpoints found in the local catalog.")
    created: list[Path] = []
    seen: set[str] = set()
    summary = {
        "dataset_id": dataset_id,
        "dry_run": dry_run,
        "validated": 0,
        "imported": 0,
        "skipped": 0,
    }
    current = "catalog"
    try:
        for checkpoint in checkpoints:
            current = checkpoint.name
            content = read_owned(source, checkpoint)
            result = decode(content)
            run_id = str(UUID(result["run_id"]))
            if run_id != result["run_id"]:
                raise ValueError("Run ID must be a canonical UUID.")
            if run_id in seen:
                raise ValueError("Duplicate run ID in catalog.")
            seen.add(run_id)
            timestamp = datetime.fromisoformat(result["created_at"])
            if timestamp.tzinfo is None:
                raise ValueError("Training timestamp must have a timezone.")
            series_hash = validate_run(result, groups, frame.attrs)
            provenance = {
                "source_run_id": run_id,
                "source_dataset_id": result["dataset_id"],
                "checkpoint_sha256": digest(content),
            }
            manifests, binaries = {}, {}
            for name in [*result["artifacts"], "calibrator"]:
                if name not in {*FAMILIES, "calibrator"}:
                    raise ValueError("Unknown model artifact.")
                directory = source / "artifacts" / run_id
                manifest = decode(read_owned(source, directory / f"{name}.json"))
                binary = read_owned(source, directory / f"{name}.joblib")
                expected = {
                    "file": f"{name}.joblib",
                    "model_name": name,
                    "sha256": digest(binary),
                    "dataset_sha256": series_hash,
                    **{
                        k: result[k]
                        for k in (
                            "dataset_id",
                            "store_id",
                            "product_id",
                            "frequency",
                            "forecast_horizon",
                        )
                    },
                }
                if any(manifest.get(k) != v for k, v in expected.items()):
                    raise ValueError(f"Artifact integrity or dataset mismatch: {name}.")
                if name != "calibrator" and result["artifacts"][name] != manifest:
                    raise ValueError(f"Checkpoint and sidecar metadata disagree: {name}.")
                if name == "calibrator" and any(
                    manifest.get(k) != result["calibration"][k]
                    for k in ("offsets", "residual_count")
                ):
                    raise ValueError("Calibrator metadata disagrees with checkpoint.")
                manifests[name] = {
                    **manifest,
                    "dataset_id": dataset_id,
                    "catalog_import": provenance,
                }
                binaries[name] = binary
            summary["validated"] += 1
            existing = session.get(AdvancedRun, run_id)
            if existing is not None:
                saved_origin = existing.result.get("catalog_import", {})
                if existing.dataset_id != dataset_id or any(
                    saved_origin.get(k) != v for k, v in provenance.items()
                ):
                    raise ValueError(
                        "Run ID already exists with different provenance; refusing to overwrite."
                    )
                # A repeated import must not report success for missing/damaged target artifacts.
                for name, manifest in manifests.items():
                    directory = storage / "artifacts" / run_id
                    if (
                        decode((directory / f"{name}.json").read_bytes()) != manifest
                        or digest((directory / f"{name}.joblib").read_bytes()) != manifest["sha256"]
                    ):
                        raise ValueError("Previously imported artifacts are missing or damaged.")
                summary["skipped"] += 1
                continue
            destination = storage / "artifacts" / run_id
            if destination.exists():
                raise ValueError("Artifact directory already exists; refusing to overwrite.")
            if dry_run:
                continue
            destination.mkdir(parents=True, exist_ok=False)
            created.append(destination)
            for name, manifest in manifests.items():
                (destination / f"{name}.joblib").write_bytes(binaries[name])
                (destination / f"{name}.json").write_text(
                    json.dumps(manifest, indent=2, allow_nan=False)
                )
            result["dataset_id"] = dataset_id
            result["configuration"]["dataset_id"] = dataset_id
            result["artifacts"] = {name: manifests[name] for name in result["artifacts"]}
            result["catalog_import"] = {
                **provenance,
                "imported_at": datetime.now(timezone.utc).isoformat(),
            }
            row = AdvancedRun(
                id=run_id,
                dataset_id=dataset_id,
                champion_model=result["champion_model"],
                created_at=timestamp,
                configuration=result["configuration"],
                result=result,
            )
            session.add(row)
            session.flush()
            session.expunge(row)
            summary["imported"] += 1
        if not dry_run:
            session.commit()
        return summary
    except Exception as exc:
        session.rollback()
        for directory in created:
            shutil.rmtree(directory)
        raise AppError(f"Catalog import rejected at {current}: {exc}", 409) from exc
