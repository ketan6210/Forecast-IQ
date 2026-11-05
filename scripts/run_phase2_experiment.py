"""Measure a full Phase 2 HTTP workflow; publish actual results, never target scores."""

import argparse
import csv
import io
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.app.main import create_app
from scripts.run_experiment import display_metric

ROOT = Path(__file__).resolve().parents[1]


def train_and_reload(client: TestClient, body: dict) -> dict:
    start = perf_counter()
    response = client.post("/forecast/train", json=body)
    response.raise_for_status()
    result = response.json()
    result["full_request_seconds"] = perf_counter() - start
    predicted = client.post("/forecast/predict", json={"run_id": result["run_id"]})
    predicted.raise_for_status()
    for first, second in zip(result["forecast"], predicted.json()["forecast"], strict=True):
        assert first["date"] == second["date"]
        np.testing.assert_allclose(
            [first[q] for q in ("p10", "p50", "p90")],
            [second[q] for q in ("p10", "p50", "p90")],
        )
    exported = client.get(f"/forecast/export/{result['run_id']}")
    exported.raise_for_status()
    assert len(list(csv.DictReader(io.StringIO(exported.text)))) == body["horizon"]
    result["artifact_reload_verified"] = True
    result["csv_export_verified"] = True
    return result


def model_table(result: dict) -> list[str]:
    lines = [
        "| Rank | Model | WAPE | sMAPE | MASE | RMSE | MAE | WAPE std |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(result["comparison"], key=lambda r: r["rank"] or 999):
        if row["status"] != "ok":
            lines.append(f"| — | {row['model']}: {row['status']} | — | — | — | — | — | — |")
            continue
        values = " | ".join(
            display_metric(m, row["summary"][m]["mean"])
            for m in ("wape", "smape", "mase", "rmse", "mae")
        )
        spread = display_metric("wape", row["summary"]["wape"]["std"])
        lines.append(f"| {row['rank']} | {row['model']} | {values} | {spread} |")
    return lines


def result_section(result: dict) -> list[str]:
    lines = [
        f"Champion: **{result['champion_model']}**, selected using mean rolling WAPE.",
        "",
        "### Rolling selection metrics (mean across folds)",
        "",
        *model_table(result),
        "",
        "### Final untouched test (calibrated P50)",
        "",
        "| Metric | Measured value |",
        "|---|---:|",
        *[f"| {m} | {display_metric(m, v)} |" for m, v in result["test_metrics"].items()],
        *[
            f"| {m} | {v:.4%} |" if m == "coverage" else f"| {m} | {v:.6f} |"
            for m, v in result["probabilistic_metrics"].items()
        ],
        "",
        "### Evaluation boundaries",
        "",
        "| Partition | Start | End | Periods |",
        "|---|---|---|---:|",
        *[
            f"| {k} | {v['start']} | {v['end']} | {v['periods']} |"
            for k, v in result["partitions"].items()
        ],
        "",
        f"- Calibration residuals: {result['calibration']['residual_count']}; "
        f"P10/P50/P90 signed offsets: `{result['calibration']['offsets']}`.",
        f"- Service training duration: {result['training_duration_seconds']:.6f} s.",
        f"- Full in-process HTTP request: {result['full_request_seconds']:.6f} s.",
        "- Saved model + calibrator reload reproduced quantiles; CSV row count verified.",
        f"- SHAP explanations calculated for: {', '.join(result['explainability']) or 'none'}.",
        "",
    ]
    lines += [f"- {r['model']}: {r['reason']}" for r in result["comparison"] if r["status"] != "ok"]
    lines += [f"- Warning: {w}" for w in result["warnings"]]
    return lines + [""]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-neural", action="store_true")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="forecastiq-phase2-") as directory:
        temp = Path(directory)
        app = create_app(f"sqlite:///{temp / 'experiment.db'}", temp / "datasets")
        with TestClient(app) as client:
            dataset_response = client.post("/datasets/demo")
            dataset_response.raise_for_status()
            dataset = dataset_response.json()
            demo = train_and_reload(
                client,
                {
                    "dataset_id": dataset["dataset_id"],
                    "store_id": "STORE_01",
                    "product_id": "SKU_001",
                    "horizon": 28,
                    "folds": 3,
                },
            )
            neural = None
            if args.include_neural:
                rng = np.random.default_rng(84)
                t = np.arange(700)
                frame = pd.DataFrame(
                    {
                        "date": pd.date_range("2023-01-01", periods=len(t)),
                        "store_id": "SYNTHETIC",
                        "product_id": "LONG_HISTORY",
                        "units_sold": rng.poisson(45 + 0.015 * t + 10 * np.sin(2 * np.pi * t / 7)),
                        "price": 10.0,
                    }
                )
                uploaded = client.post(
                    "/datasets/upload",
                    files={"file": ("long-synthetic.csv", frame.to_csv(index=False), "text/csv")},
                )
                uploaded.raise_for_status()
                neural = train_and_reload(
                    client,
                    {
                        "dataset_id": uploaded.json()["dataset_id"],
                        "store_id": "SYNTHETIC",
                        "product_id": "LONG_HISTORY",
                        "horizon": 14,
                        "folds": 3,
                        "models": ["nbeats", "lightgbm", "xgboost"],
                        "neural_epochs": 12,
                    },
                )
                assert any(
                    r["model"] == "nbeats" and r["status"] == "ok" for r in neural["comparison"]
                ), "Eligible neural example must actually train N-BEATS."
    report = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "dataset": dataset,
        "demo": demo,
        "long_synthetic_neural_example": neural,
        "note": "Synthetic experiments, not external benchmarks. Temporary artifacts are removed; "
        "normal API runs persist artifacts in STORAGE_DIR/artifacts/<run_id>.",
    }
    output = ROOT / "docs" / "phase2-measured-results.json"
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    lines = [
        "# Phase 2 measured experiments",
        "",
        f"Measured at {report['measured_at']} on `{report['environment']}`.",
        "",
        "Reproduce with `python -m scripts.run_phase2_experiment --include-neural` "
        "after installing the optional PyTorch requirements. "
        "Omit `--include-neural` for core only.",
        "",
        "These are actual, deterministic synthetic-data experiments, not external benchmark "
        "results. Timing is a single local run, excludes network transport, "
        "and is not a guarantee. "
        "The JSON report contains every fold, trial, forecast, SHAP value, and artifact manifest.",
        "",
        "## Retail demo: STORE_01 / SKU_001",
        "",
        "365 daily observations; horizon 28; three expanding folds; bounded two-setting tree "
        "search. Baselines are legitimate candidates and may beat more complex models.",
        "",
        *result_section(demo),
    ]
    if neural:
        lines += [
            "## Eligible N-BEATS example",
            "",
            "700 synthetic daily observations generated with NumPy seed 84. Poisson demand "
            "with mild trend and weekly seasonality; horizon 14; three expanding folds; "
            "12 epochs per N-BEATS fit. This is a functionality example, not a neural benchmark.",
            "",
            *result_section(neural),
        ]
    lines += [
        "## Interpretation and targets",
        "",
        "WAPE <15%, sMAPE <18%, MASE <0.9 and interval coverage near 80–90% are objectives, "
        "not acceptance criteria for software correctness. The short demo can miss these "
        "objectives. No parameter or interval was chosen using final-test performance.",
        "",
        "Intervals use separate prequential signed residuals pooled across forecast leads. "
        "Small calibration samples, time dependence and distribution changes can cause "
        "substantial undercoverage. These empirical marginal intervals carry no unconditional "
        "coverage guarantee. Refitting on all history happens only after test evaluation.",
        "",
    ]
    (ROOT / "docs" / "phase2-measured-results.md").write_text("\n".join(lines))
    print(
        json.dumps(
            {
                "champion": demo["champion_model"],
                **demo["test_metrics"],
                **demo["probabilistic_metrics"],
            },
            indent=2,
        )
    )
    print(f"Results saved to {output}")


if __name__ == "__main__":
    main()
