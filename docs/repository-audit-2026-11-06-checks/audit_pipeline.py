"""Reproducible audit probes; writes evidence, never changes application source/data."""

import json
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.main import create_app  # noqa: E402
from backend.app.services.catalog_import import import_catalog  # noqa: E402
from scripts.run_phase2_experiment import train_and_reload  # noqa: E402
from scripts.run_phase3_experiment import experiment  # noqa: E402

OUT = Path(__file__).resolve().parent


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def checked(response):
    response.raise_for_status()
    return response.json()


def summarize(run):
    return {
        key: run[key]
        for key in (
            "run_id", "champion_model", "frequency", "forecast_horizon", "configuration",
            "comparison", "test_metrics", "probabilistic_metrics", "test_predictions",
            "forecast", "partitions", "calibration", "artifacts", "warnings",
        )
    }


def verify_metrics(run):
    rows = run["test_predictions"]
    actual = np.array([r["actual"] for r in rows])
    q = np.array([[r[k] for k in ("p10", "p50", "p90")] for r in rows])
    delta = abs(actual - q[:, 1])
    independently_computed = {
        "mae": float(delta.mean()),
        "rmse": float(np.sqrt(np.mean(delta**2))),
        "wape": float(delta.sum() / actual.sum()),
        "smape": float(np.mean(2 * delta / (abs(actual) + abs(q[:, 1])))),
    }
    for name, value in independently_computed.items():
        np.testing.assert_allclose(value, run["test_metrics"][name])
    for i, tau in enumerate((0.1, 0.5, 0.9)):
        residual = actual - q[:, i]
        value = float(np.maximum(tau * residual, (tau - 1) * residual).mean())
        np.testing.assert_allclose(value, run["probabilistic_metrics"][f"pinball_p{int(100*tau)}"])
    coverage = float(((actual >= q[:, 0]) & (actual <= q[:, 2])).mean())
    np.testing.assert_allclose(coverage, run["probabilistic_metrics"]["coverage"])
    assert np.all(np.diff(q, axis=1) >= 0)
    assert all(r["training_end"] < r["date"] < run["partitions"]["test"]["start"]
               for r in run["calibration"]["records"])
    return {**independently_computed, "coverage": coverage, "ordered_quantiles": True}


with TemporaryDirectory(prefix="forecastiq-audit-20261106-") as folder:
    temp = Path(folder)
    app = create_app(f"sqlite:///{temp / 'audit.db'}", temp / "storage")
    with TestClient(app) as client:
        # Execute the existing real forecast/inventory walkthrough without overwriting its
        # historical reports. Business inventory and cost inputs are explicit demo assumptions.
        inventory = experiment(client, "in-process temporary SQLite audit")
        save("inventory-pipeline.json", inventory)
        run = checked(client.get(f"/forecast/runs/{inventory['forecast_run_id']}"))
        forecast = summarize(run)
        forecast["independent_metric_check"] = verify_metrics(run)
        forecast["artifact_reload_exact"] = checked(client.post(
            "/forecast/predict", json={"run_id": run["run_id"]}
        ))["forecast"] == run["forecast"]
        assert forecast["artifact_reload_exact"]
        forecast["explainability_models"] = list(run["explainability"])
        save("forecast-pipeline.json", forecast)
        print("demo forecast, inventory, simulation and 1000-location benchmark passed", flush=True)

        # A neural-eligible history verifies the entire training API, not only the class.
        rng = np.random.default_rng(84)
        t = np.arange(700)
        frame = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=len(t)),
            "store_id": "AUDIT", "product_id": "NEURAL",
            "units_sold": rng.poisson(45 + .015*t + 10*np.sin(2*np.pi*t/7)),
            "price": 10.,
        })
        dataset = checked(client.post("/datasets/upload", files={
            "file": ("neural-audit.csv", frame.to_csv(index=False), "text/csv")
        }))
        neural = train_and_reload(client, {
            "dataset_id": dataset["dataset_id"], "store_id": "AUDIT", "product_id": "NEURAL",
            "horizon": 14, "folds": 3, "models": ["nbeats", "lightgbm", "xgboost"],
            "neural_epochs": 2, "tuning_trials": 2,
        })
        assert next(r for r in neural["comparison"] if r["model"] == "nbeats")["status"] == "ok"
        save("neural-pipeline.json", {**summarize(neural),
             "artifact_reload_verified": neural["artifact_reload_verified"],
             "csv_export_verified": neural["csv_export_verified"],
             "independent_metric_check": verify_metrics(neural)})
        print("eligible neural API training, persistence and quantiles passed", flush=True)

        # Minimal accepted schema exposes the stale hard-coded quality-screen label.
        minimal = frame[["date", "units_sold"]].iloc[:140]
        mapped = checked(client.post("/datasets/upload", files={
            "file": ("two-columns.csv", minimal.to_csv(index=False), "text/csv")
        }, data={"store_column": "__single__", "product_column": "__single__"}))
        save("minimal-schema.json", {"source_columns": list(minimal.columns), "response": mapped})

        # Verify every existing checkpoint and binary against the full source dataset.
        source = ROOT / "storage/kaggle-batch"
        with (ROOT / "data/imports/kaggle-store-item-sales.csv").open("rb") as handle:
            catalog_dataset = checked(client.post("/datasets/upload", files={
                "file": ("catalog-audit.csv", handle, "text/csv")
            }))
        dataset_id = catalog_dataset["dataset_id"]
        catalog = {"source": str(source.relative_to(ROOT)), "dataset_rows": catalog_dataset["row_count"]}
        for label, dry_run in (("dry_run", True), ("registration", False), ("repeat", False)):
            start = perf_counter()
            with app.state.session_factory() as session:
                result = import_catalog(session, app.state.storage, source, dataset_id, dry_run=dry_run)
            catalog[label] = {**result, "seconds": perf_counter() - start}
            print("catalog", label, result, flush=True)
        saved = []
        page_sizes = []
        for offset in range(0, 601, 100):
            page = checked(client.get("/forecast/models", params={"dataset_id": dataset_id, "offset": offset}))
            page_sizes.append(len(page))
            saved.extend(page)
            if not page:
                break
        assert len(saved) == len({r["run_id"] for r in saved}) == 500
        catalog["page_sizes"] = page_sizes
        catalog["champions"] = dict(Counter(r["champion_model"] for r in saved))
        samples = []
        for row in saved[::100]:
            original = checked(client.get(f"/forecast/runs/{row['run_id']}"))
            predicted = checked(client.post("/forecast/predict", json={"run_id": row["run_id"]}))
            assert predicted["forecast"] == original["forecast"]
            samples.append({"run_id": row["run_id"], "champion": row["champion_model"],
                            "points": len(predicted["forecast"]), "exact_match": True})
        catalog["sampled_artifact_reloads"] = samples
        start = perf_counter()
        batch = checked(client.post("/inventory/batch", json={"items": [{
            "forecast_run_id": row["run_id"], "on_hand_inventory": 0,
            "on_order_inventory": 10000, "incoming_orders": [{"period": 20, "quantity": 10000}],
            "lead_time": 7, "uncertainty_samples": 100,
        } for row in saved]}))
        assert batch["successful"] == 500 and batch["failed"] == 0
        assert all(p["expedite_needed"] and p["recommended_order_quantity"] == 0 for p in batch["items"])
        catalog["inventory_batch"] = {"successful": batch["successful"], "failed": batch["failed"],
                                      "seconds": perf_counter()-start, "portfolio": batch["portfolio"],
                                      "assumptions": "0 on hand; 10000 due period 20; lead time 7; 100 samples. Not observed business stock."}
        catalog["kpis"] = checked(client.get("/inventory/kpis", params={"dataset_id": dataset_id}))
        assert catalog["kpis"]["series_count"] == 500
        catalog["artifacts_checked"] = len(list((source / "artifacts").glob("*/*.joblib")))
        catalog["scope"] = "Temporary SQLite registration; no existing database or source artifact changed; no catalog retraining."
        save("catalog.json", catalog)
        print("500-series catalog integration and five champion/calibrator reloads passed", flush=True)
