import copy

import pandas as pd
import pytest

from backend.app.evaluation.operational import evaluate_catalog, score_predictions


def example():
    history = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=6).strftime("%Y-%m-%d"),
            "store": "s",
            "item": "p",
            "sales": [1, 2, 3, 4, 5, 15],
        }
    )
    run = {
        "run_id": "r",
        "store_id": "s",
        "product_id": "p",
        "champion_model": "naive",
        "forecast_horizon": 2,
        "frequency": "D",
        "partitions": {
            "selection": {"end": "2025-01-02"},
            "calibration": {"start": "2025-01-03", "end": "2025-01-04"},
            "test": {"start": "2025-01-05", "end": "2025-01-06", "periods": 2},
        },
        "test_predictions": [
            {"date": "2025-01-05", "actual": 5, "p10": 2, "p50": 6, "p90": 10},
            {"date": "2025-01-06", "actual": 15, "p10": 2, "p50": 6, "p90": 10},
        ],
    }
    return history, run


def test_observed_coverage_by_hand_and_supplier_results_remain_unverified():
    history, run = example()
    result = evaluate_catalog([run], history)
    assert result["aggregate"]["coverage"] == 0.5
    assert result["aggregate"]["wape"] == 0.5
    assert result["aggregate"]["mae"] == 5
    assert result["by_lead"][0]["coverage"] == 1
    assert result["by_lead"][1]["coverage"] == 0
    assert result["operational_validation"]["observed_fill_rate"] is None
    assert result["operational_validation"]["observed_cycle_service"] is None


@pytest.mark.parametrize(
    "damage", ["actual", "crossing", "duplicate_run", "overlap", "duplicate_history"]
)
def test_untrustworthy_holdout_evidence_rejected(damage):
    history, run = example()
    runs = [run]
    if damage == "actual":
        run["test_predictions"][0]["actual"] = 99
    elif damage == "crossing":
        run["test_predictions"][0]["p10"] = 100
    elif damage == "duplicate_run":
        runs.append(copy.deepcopy(run))
    elif damage == "overlap":
        run["partitions"]["calibration"]["end"] = "2025-01-05"
    else:
        history = pd.concat([history, history])
    with pytest.raises(ValueError):
        evaluate_catalog(runs, history)


def test_zero_observations_have_no_invented_wape():
    points = pd.DataFrame({"actual": [0, 0], "p10": [0, 0], "p50": [0, 0], "p90": [0, 0]})
    assert score_predictions(points)["wape"] is None
    assert score_predictions(points)["smape"] == 0


def test_normalized_history_has_the_same_measured_coverage():
    history, run = example()
    canonical = history.rename(
        columns={"store": "store_id", "item": "product_id", "sales": "units_sold"}
    )
    assert evaluate_catalog([run], canonical) == evaluate_catalog([run], history)
