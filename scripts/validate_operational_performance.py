"""Recompute saved holdout coverage; leave unavailable supplier/service outcomes unverified."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backend.app.evaluation.operational import evaluate_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("storage/kaggle-batch"))
    parser.add_argument(
        "--history", type=Path, default=Path("data/imports/kaggle-store-item-sales.csv")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("docs/operational-validation-2026-11-11.json")
    )
    args = parser.parse_args()
    paths = sorted((args.catalog / "runs").glob("*.json"))
    contents = [p.read_bytes() for p in paths]
    history = pd.read_csv(
        args.history,
        dtype={
            "store": str,
            "item": str,
            "store_id": str,
            "product_id": str,
        },
    )
    result = evaluate_catalog([json.loads(content) for content in contents], history)
    result.update(
        measured_at=datetime.now(timezone.utc).isoformat(),
        history_file=str(args.history),
        history_rows=len(history),
        history_sha256=hashlib.sha256(args.history.read_bytes()).hexdigest(),
        catalog_sha256=hashlib.sha256(b"".join(contents)).hexdigest(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "report": str(args.output),
                "series": result["series_count"],
                "aggregate": result["aggregate"],
                "operational_validation": result["operational_validation"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
