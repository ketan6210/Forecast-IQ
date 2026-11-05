"""Create local Kaggle predictions with ForecastIQ's chronological training pipeline."""

import argparse
import hashlib
import json
import logging
import multiprocessing
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import numpy as np
import pandas as pd

from backend.app.data.loader import read_csv
from backend.app.data.validator import DataValidator
from backend.app.schemas.advanced import TrainingRequest
from backend.app.services.advanced_training import train_advanced

ROOT = Path(__file__).resolve().parents[1]
CONFIGURATION = {
    "horizon": 90,
    "folds": 3,
    "frequency": "daily",
    "window": "expanding",
    "models": ["ets", "lightgbm", "xgboost"],
    "tune": False,
    "tuning_seed": 42,
}


def write_json(path: Path, value: dict):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def train_one(frame: pd.DataFrame, dataset_id: str, storage: str) -> str:
    """Workers save models locally; no requests or writes go to the live app database."""
    logging.getLogger("forecastiq.advanced").setLevel(logging.ERROR)
    store, item = str(frame.store_id.iloc[0]), str(frame.product_id.iloc[0])
    root = Path(storage)
    path = root / "runs" / f"store-{store}-item-{item}.json"
    request = TrainingRequest(
        dataset_id=dataset_id,
        store_id=store,
        product_id=item,
        **CONFIGURATION,
    )
    frame.attrs.update(frequency="D", external_features=[])
    run_id = str(uuid4())
    result = train_advanced(frame, request, run_id, root / "artifacts" / run_id)
    write_json(path, result)
    return str(path)


def export_results(paths: list[Path], test: pd.DataFrame, sample: pd.DataFrame, output: Path):
    forecasts, historical, rows, candidate_failures = [], [], [], []
    for path in paths:
        run = json.loads(path.read_text())
        common = {"store": run["store_id"], "item": run["product_id"]}
        forecasts.extend({**common, **point} for point in run["forecast"])
        historical.extend({**common, **point} for point in run["test_predictions"])
        champion = next(c for c in run["comparison"] if c["model"] == run["champion_model"])
        rows.append(
            {
                **common,
                "run_id": run["run_id"],
                "champion": run["champion_model"],
                "selection_wape": champion["summary"]["wape"]["mean"],
                **{f"test_{k}": v for k, v in run["test_metrics"].items()},
                "coverage": run["probabilistic_metrics"]["coverage"],
                "forecast_units": sum(point["p50"] for point in run["forecast"]),
                "training_seconds": run["training_duration_seconds"],
                "test_start": run["partitions"]["test"]["start"],
                "test_end": run["partitions"]["test"]["end"],
            }
        )
        candidate_failures.extend(
            {**common, "model": row["model"], "reason": row.get("reason")}
            for row in run["comparison"]
            if row["status"] != "ok"
        )

    future = pd.DataFrame(forecasts)
    merged = test.merge(future, on=["date", "store", "item"], how="left", validate="one_to_one")
    if len(merged) != len(test) or merged[["p10", "p50", "p90"]].isna().any().any():
        raise ValueError("Every test ID must have a prediction before a submission is written.")
    values = merged[["p10", "p50", "p90"]].to_numpy()
    if not np.isfinite(values).all() or (values < 0).any() or (np.diff(values, axis=1) < 0).any():
        raise ValueError("Forecasts must be finite, nonnegative and ordered.")
    submission = sample[["id"]].merge(
        merged[["id", "p50"]].rename(columns={"p50": "sales"}),
        on="id",
        validate="one_to_one",
        how="left",
    )
    if not submission.id.equals(sample.id) or submission.sales.isna().any():
        raise ValueError("Submission IDs must match the supplied template in its original order.")
    history = pd.DataFrame(historical)
    by_series = pd.DataFrame(rows)
    errors = np.abs(history.actual - history.p50)
    denominator = np.abs(history.actual) + np.abs(history.p50)
    smape = np.divide(
        2 * errors.to_numpy(),
        denominator.to_numpy(),
        out=np.zeros(len(history)),
        where=denominator.to_numpy() != 0,
    )
    summary = {
        "completed_series": len(rows),
        "prediction_rows": len(submission),
        "test_period": {"start": str(test.date.min()), "end": str(test.date.max())},
        "historical_test_period": {
            "start": str(history.date.min()),
            "end": str(history.date.max()),
        },
        "historical_test_rows": len(history),
        "aggregate_test_wape": float(errors.sum() / history.actual.sum()),
        "aggregate_test_mae": float(errors.mean()),
        "aggregate_test_rmse": float(np.sqrt(np.square(errors).mean())),
        "aggregate_test_smape": float(smape.mean()),
        "aggregate_interval_coverage": float(
            ((history.actual >= history.p10) & (history.actual <= history.p90)).mean()
        ),
        "median_series_test_wape": float(by_series.test_wape.median()),
        "total_forecast_units": float(submission.sales.sum()),
        "champion_counts": dict(Counter(by_series.champion)),
        "candidate_failures": candidate_failures,
        "note": "Metrics use held-out historical sales. Kaggle test.csv has no labels; "
        "sample_submission.csv supplies IDs and output format only. Predictions are daily P50 "
        "estimates, not guaranteed quantities. No Kaggle score or submission is claimed.",
    }
    submission.to_csv(output / "submission.csv", index=False)
    merged.to_csv(output / "predictions-with-intervals.csv", index=False)
    history.to_csv(output / "historical-test-predictions.csv", index=False)
    by_series.to_csv(output / "series-results.csv", index=False)
    monthly = merged.assign(month=merged.date.str[:7]).groupby("month").p50.sum()
    monthly.rename("forecast_units").to_csv(output / "monthly-forecast.csv")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/kaggle-batch")
    parser.add_argument("--storage-dir", type=Path, default=ROOT / "storage/kaggle-batch")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("Use between one and four worker processes.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.storage_dir / "runs").mkdir(parents=True, exist_ok=True)
    (args.storage_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    paths = {
        name: args.input_dir / name for name in ("train.csv", "test.csv", "sample_submission.csv")
    }
    # A checkpoint belongs to these inputs, settings and source files, not just its filename.
    source_paths = sorted((ROOT / "backend/app").rglob("*.py")) + [Path(__file__).resolve()]
    code_hash = hashlib.sha256()
    for path in source_paths:
        code_hash.update(str(path.relative_to(ROOT)).encode())
        code_hash.update(path.read_bytes())
    manifest = {
        "dataset_id": args.dataset_id,
        "configuration": CONFIGURATION,
        "source_sha256": code_hash.hexdigest(),
        "input_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()
        },
        "storage": str(args.storage_dir.resolve()),
        "live_app_database_modified": False,
    }
    checkpoint = args.storage_dir / "manifest.json"
    if checkpoint.exists() and json.loads(checkpoint.read_text()) != manifest:
        raise ValueError(
            "Existing checkpoints use different inputs/code/configuration. "
            "Use a new storage directory."
        )
    write_json(checkpoint, manifest)

    frame = read_csv(paths["train.csv"].read_bytes()).rename(
        columns={"store": "store_id", "item": "product_id", "sales": "units_sold"}
    )
    frame, report = DataValidator().validate(frame, "daily")
    if report.validation_status == "FAIL":
        raise ValueError(report.errors)
    test = pd.read_csv(paths["test.csv"], dtype={"store": "string", "item": "string"})
    sample = pd.read_csv(paths["sample_submission.csv"])
    if list(sample.columns) != ["id", "sales"] or not test.id.is_unique or not sample.id.is_unique:
        raise ValueError("Invalid test/submission template schema or duplicate IDs.")
    if set(test.id) != set(sample.id):
        raise ValueError("Test and submission template IDs differ.")
    groups = {
        key: group.reset_index(drop=True)
        for key, group in frame.groupby(["store_id", "product_id"])
    }
    test_groups = dict(tuple(test.groupby(["store", "item"])))
    if set(groups) != set(test_groups):
        raise ValueError("Training and test series must match exactly.")
    for key, group in test_groups.items():
        expected = pd.date_range(groups[key].date.max() + pd.Timedelta(days=1), periods=90)
        if sorted(group.date.tolist()) != expected.strftime("%Y-%m-%d").tolist():
            raise ValueError(f"Unexpected test calendar for {key}.")
    result_paths = {
        key: args.storage_dir / "runs" / f"store-{key[0]}-item-{key[1]}.json" for key in groups
    }
    pending = {key: frame for key, frame in groups.items() if not result_paths[key].exists()}
    completed = len(groups) - len(pending)
    print(
        json.dumps(
            {
                "series": len(groups),
                "rows": len(frame),
                "resumed_series": completed,
                "workers": args.workers,
            }
        ),
        flush=True,
    )
    started = perf_counter()
    failures = []
    with ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        jobs = {
            pool.submit(train_one, group, args.dataset_id, str(args.storage_dir)): key
            for key, group in pending.items()
        }
        for future in as_completed(jobs):
            key = jobs[future]
            try:
                future.result()
                completed += 1
            except Exception as exc:
                failures.append({"store": key[0], "item": key[1], "error": str(exc)})
                print(json.dumps({"failed_series": failures[-1]}), flush=True)
            if completed % 25 == 0 or completed == len(groups):
                print(
                    json.dumps(
                        {
                            "completed": completed,
                            "total": len(groups),
                            "elapsed_seconds": round(perf_counter() - started, 1),
                        }
                    ),
                    flush=True,
                )
    if failures:
        write_json(args.output_dir / "failures.json", {"failures": failures})
        raise RuntimeError(
            "Some series failed. Completed checkpoints are retained; "
            "no final submission was written."
        )
    summary = export_results(list(result_paths.values()), test, sample, args.output_dir)
    summary.update(
        completed_at=datetime.now(timezone.utc).isoformat(),
        wall_seconds_this_execution=perf_counter() - started,
        configuration=CONFIGURATION,
        provenance=manifest,
    )
    write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
