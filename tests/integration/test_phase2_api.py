import pandas as pd
import pytest

from backend.app.schemas.advanced import TrainingRequest
from backend.app.services.advanced_training import train_advanced


def uploaded(client, frame):
    response = client.post(
        "/datasets/upload", files={"file": ("sales.csv", frame.to_csv(index=False), "text/csv")}
    )
    assert response.status_code == 201, response.text
    return response.json()["dataset_id"]


def test_full_advanced_api_pipeline(client):
    dataset_id = client.post("/datasets/demo").json()["dataset_id"]
    body = {
        "dataset_id": dataset_id,
        "store_id": "STORE_01",
        "product_id": "SKU_001",
        "horizon": 7,
        "folds": 2,
    }
    response = client.post("/forecast/train", json=body)
    assert response.status_code == 201, response.text
    result = response.json()
    assert {"lightgbm", "xgboost"}.issubset(result["artifacts"])
    assert len(result["comparison"]) == 10
    assert result["partitions"]["selection"]["end"] < result["partitions"]["calibration"]["start"]
    assert result["partitions"]["calibration"]["end"] < result["partitions"]["test"]["start"]
    assert all(
        r["training_end"] < r["date"] < result["partitions"]["test"]["start"]
        for r in result["calibration"]["records"]
    )
    forecast = result["forecast"]
    assert all(0 <= p["p10"] <= p["p50"] <= p["p90"] for p in forecast)
    run = result["run_id"]
    assert client.get(f"/forecast/runs/{run}").json() == result
    predicted = client.post("/forecast/predict", json={"run_id": run}).json()
    for original, reloaded in zip(forecast, predicted["forecast"], strict=True):
        assert original["p50"] == pytest.approx(reloaded["p50"])
    assert client.post("/forecast/predict", json={"run_id": run, "horizon": 30}).status_code == 422
    assert len(client.get(f"/forecast/model-comparison?run_id={run}").json()) == 10
    assert len(client.get(f"/forecast/backtest?run_id={run}").json()["folds"]) == 2
    assert client.get(f"/forecast/explainability?run_id={run}&model=xgboost").status_code == 200
    assert client.get(f"/forecast/explainability?run_id={run}&model=arima").status_code == 404
    export = client.get(f"/forecast/export/{run}")
    assert export.status_code == 200 and export.text.startswith("date,p10,p50,p90")
    assert len(export.text.strip().splitlines()) == 8
    models = client.get(f"/forecast/models?dataset_id={dataset_id}").json()
    assert models[0]["run_id"] == run
    comparison = client.post(
        "/forecast/series-comparison",
        json={
            "dataset_id": dataset_id,
            "series": [
                {"store_id": "STORE_01", "product_id": "SKU_001"},
                {"store_id": "STORE_02", "product_id": "SKU_001"},
            ],
        },
    ).json()
    assert comparison["series"][0]["status"] == "ok"
    assert comparison["series"][1]["status"] == "not_trained"


@pytest.mark.parametrize("frequency", ["W-MON", "MS", "ME"])
def test_weekly_monthly_end_to_end(client, series, frequency):
    series["date"] = pd.date_range("2015-01-01", periods=len(series), freq=frequency)
    dataset_id = uploaded(client, series)
    report = client.get(f"/datasets/{dataset_id}").json()
    assert report["frequency"] == frequency
    assert report["missing_date_count"] == 0
    response = client.post(
        "/forecast/train",
        json={
            "dataset_id": dataset_id,
            "store_id": "S1",
            "product_id": "P1",
            "horizon": 7,
            "folds": 2,
            "models": ["ets", "lightgbm", "xgboost"],
            "tune": False,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["frequency"] == frequency
    expected = (
        pd.date_range(series.date.iloc[-1], periods=8, freq=frequency)[1:]
        .strftime("%Y-%m-%d")
        .tolist()
    )
    assert [p["date"] for p in response.json()["forecast"]] == expected


def test_custom_target_time_and_sku_mapping(client, series):
    frame = series.rename(
        columns={"date": "week_start", "units_sold": "demand", "product_id": "sku_id"}
    )
    response = client.post(
        "/datasets/upload",
        files={"file": ("mapped.csv", frame.to_csv(index=False), "text/csv")},
        data={"date_column": "week_start", "target_column": "demand"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["column_mapping"]["units_sold"] == "demand"
    dataset = response.json()["dataset_id"]
    assert client.get(f"/datasets/{dataset}/options").json()["products"] == ["P1"]


def test_failed_advanced_candidate_does_not_block_baselines(client, series, monkeypatch):
    from backend.app.models.lightgbm_model import LightGBMModel

    def fail(*args, **kwargs):
        raise ValueError("deliberate fit failure")

    monkeypatch.setattr(LightGBMModel, "fit", fail)
    dataset_id = uploaded(client, series)
    response = client.post(
        "/forecast/train",
        json={
            "dataset_id": dataset_id,
            "store_id": "S1",
            "product_id": "P1",
            "horizon": 7,
            "folds": 2,
            "models": ["lightgbm", "nbeats"],
        },
    )
    assert response.status_code == 201, response.text
    rows = {row["model"]: row for row in response.json()["comparison"]}
    assert rows["lightgbm"]["status"] == "failed"
    assert rows["nbeats"]["status"] == "skipped"
    assert response.json()["champion_model"] in {"naive", "seasonal_naive", "moving_average"}


def test_final_test_changes_do_not_change_calibration_or_selection(series, tmp_path):
    req = TrainingRequest(
        dataset_id="test",
        store_id="S1",
        product_id="P1",
        horizon=7,
        folds=2,
        models=["lightgbm"],
        tune=False,
    )
    original = train_advanced(series, req, "original", tmp_path / "original")
    changed = series.copy()
    changed.loc[len(series) - 7 :, ["units_sold", "price"]] = 999
    perturbed = train_advanced(changed, req, "changed", tmp_path / "changed")
    assert original["champion_model"] == perturbed["champion_model"]
    assert original["calibration"] == perturbed["calibration"]
    for before, after in zip(
        original["test_predictions"], perturbed["test_predictions"], strict=True
    ):
        assert before["p10"] == after["p10"]
        assert before["p50"] == after["p50"]
        assert before["p90"] == after["p90"]
    assert original["test_metrics"] != perturbed["test_metrics"]


def test_undefined_wape_and_zero_demand_are_honest(client, series):
    series["units_sold"] = 0
    dataset = uploaded(client, series)
    response = client.post(
        "/forecast/train",
        json={
            "dataset_id": dataset,
            "store_id": "S1",
            "product_id": "P1",
            "horizon": 7,
            "folds": 2,
            "models": ["naive"],
        },
    )
    assert response.status_code == 201
    result = response.json()
    assert result["champion_model"] == "naive"
    assert result["test_metrics"]["wape"] is None
    assert result["test_metrics"]["mase"] is None
    assert "undefined" in result["selection_reason"]
    assert result["probabilistic_metrics"]["coverage"] == 1


@pytest.mark.parametrize(
    "extra", [{"horizon": 0}, {"horizon": 91}, {"folds": 1}, {"models": ["fake"]}]
)
def test_invalid_configuration(client, series, extra):
    dataset = uploaded(client, series)
    response = client.post(
        "/forecast/train",
        json={"dataset_id": dataset, "store_id": "S1", "product_id": "P1", **extra},
    )
    assert response.status_code == 422
