"""Reproduce the completion audit's measured forecast and inventory examples."""

import argparse
import json
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from scripts.run_phase3_experiment import experiment, post

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--legacy-run", help="Optional existing run to verify after the upgrade")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=240) as client:
        result = experiment(client, args.base_url)
        run = client.get(f"/forecast/runs/{result['forecast_run_id']}")
        run.raise_for_status()
        result["comparison"] = run.json()["comparison"]
        result["artifacts"] = run.json()["artifacts"]
        restored = post(client, "/forecast/predict", {"run_id": result["forecast_run_id"]})
        assert restored["forecast"] == result["forecast"]
        result["champion_reload_equal"] = True
        if args.legacy_run:
            old = client.get(f"/forecast/runs/{args.legacy_run}")
            old.raise_for_status()
            loaded = post(client, "/forecast/predict", {"run_id": args.legacy_run})
            assert loaded["forecast"] == old.json()["forecast"]
            result["legacy_artifact"] = {"run_id": args.legacy_run, "forecast_equal": True}
        # Explicitly synthetic longer history makes every N-BEATS training fold eligible.
        rng = np.random.default_rng(84)
        t = np.arange(700)
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2023-01-01", periods=len(t)),
                "units_sold": rng.poisson(45 + 0.015 * t + 10 * np.sin(2 * np.pi * t / 7)),
            }
        )
        response = client.post(
            "/datasets/upload",
            files={"file": ("long-neural-demand.csv", frame.to_csv(index=False), "text/csv")},
            data={"store_column": "__single__", "product_column": "__single__"},
        )
        response.raise_for_status()
        neural = post(
            client,
            "/forecast/train",
            {
                "dataset_id": response.json()["dataset_id"],
                "store_id": "ALL_STORES",
                "product_id": "ALL_PRODUCTS",
                "horizon": 14,
                "folds": 3,
                "models": ["nbeats"],
                "neural_epochs": 12,
            },
        )
        candidate = next(row for row in neural["comparison"] if row["model"] == "nbeats")
        assert candidate["status"] == "ok", candidate
        reloaded = post(client, "/forecast/predict", {"run_id": neural["run_id"]})
        assert reloaded["forecast"] == neural["forecast"]
        result["long_history_neural"] = neural
        result["long_history_neural"]["data_note"] = (
            "700 synthetic daily Poisson counts, seed 84, trend and weekly seasonality; "
            "12 N-BEATS epochs. This is an execution check, not a retail benchmark."
        )
    path = ROOT / "docs/completion-measured-results.json"
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "report": str(path),
                "dataset_id": result["dataset_id"],
                "plan_id": result["recommendation"]["plan_id"],
                "champion": result["champion_model"],
                "test_metrics": result["test_metrics"],
                "neural_run_id": neural["run_id"],
                "neural_status": candidate["status"],
                "neural_champion": neural["champion_model"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
