"""Reproduce an actual demo experiment and write measured results, never placeholders."""

import json
import platform
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from fastapi.testclient import TestClient

from backend.app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def display_metric(name: str, value: float | None) -> str:
    if value is None:
        return "undefined"
    return f"{value * 100:.3f}%" if name in {"wape", "smape"} else f"{value:.4f}"


def main() -> None:
    with TemporaryDirectory(prefix="forecastiq-experiment-") as directory:
        temp = Path(directory)
        app = create_app(f"sqlite:///{temp / 'experiment.db'}", temp / "datasets")
        with TestClient(app) as client:
            response = client.post("/datasets/demo")
            response.raise_for_status()
            dataset = response.json()
            start = perf_counter()
            response = client.post(
                "/forecast",
                json={
                    "dataset_id": dataset["dataset_id"],
                    "store_id": "STORE_01",
                    "product_id": "SKU_001",
                    "horizon": 28,
                },
            )
            response.raise_for_status()
            elapsed = perf_counter() - start
            forecast = response.json()
    report = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": version("numpy"),
            "pandas": version("pandas"),
            "scikit_learn": version("scikit-learn"),
        },
        "dataset": dataset,
        "forecast": forecast,
        "full_forecast_request_seconds": elapsed,
    }
    output = ROOT / "docs" / "measured-results.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    metrics = ["mae", "rmse", "wape", "smape", "mase"]
    lines = [
        "# Measured synthetic-demo experiment",
        "",
        f"Run at {report['measured_at']}. Reproduce with `python -m scripts.run_experiment`.",
        "",
        "These are actual local measurements on synthetic data, not external benchmark results.",
        "One series: **STORE_01 / SKU_001**, requested horizon **28 days**.",
        "",
        f"- Data: {dataset['row_count']:,} rows; {dataset['store_count']} stores; "
        f"{dataset['product_count']} products; {dataset['date_min']} → {dataset['date_max']}.",
        f"- Missing rate: {dataset['missing_rate']:.2%}.",
        f"- Selected baseline: **{forecast['model']}**, based only on validation WAPE.",
        f"- Forecast total: **{forecast['summary']['forecast_total']:.2f} units**.",
        "",
    ]
    for partition in ("validation", "test"):
        lines += [
            f"## {partition.title()} metrics",
            "",
            "| Model | MAE | RMSE | WAPE | sMAPE | MASE |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for row in forecast["comparison"]:
            values = " | ".join(
                display_metric(key, row[f"{partition}_metrics"][key]) for key in metrics
            )
            lines.append(f"| {row['model']} | {values} |")
        lines.append("")
    lines += ["## System timings", "", "| Operation | Seconds |", "|---|---:|"]
    timings = {
        **dataset["timings"],
        **forecast["timings"],
        "full_forecast_request_seconds": elapsed,
    }
    lines += [f"| {name} | {value:.6f} |" for name, value in timings.items()]
    lines += [
        "",
        "Training includes fitting all four models, validation forecasting, test refits and "
        "forecasting, and fitting the selected model on all history. Forecast generation is "
        "prediction-only latency after that final fit. Full request timing includes loading "
        "and persistence via the in-process HTTP test client, but excludes network transport.",
        "",
        "Timing is one local run, not a performance benchmark or latency guarantee.",
        "",
        "## Split",
        "",
        "| Partition | Start | End | Days |",
        "|---|---|---|---:|",
    ]
    lines += [
        f"| {name} | {part['start']} | {part['end']} | {part['days']} |"
        for name, part in forecast["split"].items()
    ]
    lines += [
        "",
        "Each holdout uses a fixed forecast origin. Future prices are carried from the "
        "last known price; future promotion, discount and holiday indicators are zero.",
        "",
        f"Environment: `{report['environment']}`",
        "",
    ]
    (ROOT / "docs" / "measured-results.md").write_text("\n".join(lines))
    print(f"Selected {forecast['model']}; test WAPE={forecast['test_metrics']['wape']:.6f}")
    print(f"Results saved to {output}")


if __name__ == "__main__":
    main()
