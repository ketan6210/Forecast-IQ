import pytest
from sqlalchemy import select

from backend.app.db.models import ForecastRun


def upload(client, frame):
    return client.post(
        "/datasets/upload", files={"file": ("sales.csv", frame.to_csv(index=False), "text/csv")}
    )


def test_complete_demo_pipeline_and_persistence(client):
    response = client.post("/datasets/demo")
    assert response.status_code == 201, response.text
    metadata = response.json()
    assert metadata["row_count"] == 4380
    assert metadata["store_count"] == 2
    assert metadata["product_count"] == 6
    assert metadata["is_demo"] is True
    assert metadata["validation_status"] == "PASS"
    dataset_id = metadata["dataset_id"]
    options = client.get(f"/datasets/{dataset_id}/options").json()
    assert len(options["store_products"]["STORE_01"]) == 6
    result = client.post(
        "/forecast",
        json={
            "dataset_id": dataset_id,
            "store_id": "STORE_01",
            "product_id": "SKU_001",
            "horizon": 28,
        },
    )
    assert result.status_code == 200, result.text
    forecast = result.json()
    assert len(forecast["forecast"]) == 28
    assert forecast["forecast"][0]["date"] == "2026-01-01"
    assert len(forecast["comparison"]) == 4
    assert forecast["metrics"] == forecast["test_metrics"]
    assert forecast["split"]["train"]["end"] < forecast["split"]["validation"]["start"]
    expected = min(
        forecast["comparison"],
        key=lambda r: (
            r["validation_metrics"]["wape"],
            r["validation_metrics"]["mase"],
            r["model"],
        ),
    )
    assert forecast["model"] == expected["model"]
    assert client.get(f"/forecasts/{forecast['run_id']}").json() == forecast
    with client.app.state.session_factory() as session:
        stored = session.scalar(select(ForecastRun))
        assert stored.selected_model == forecast["model"]
        assert stored.validation_metrics == forecast["validation_metrics"]
    assert all(value >= 0 for value in forecast["timings"].values())


@pytest.mark.parametrize("horizon", [7, 14, 28])
def test_uploaded_csv_can_be_forecast(client, series, horizon):
    response = upload(client, series)
    assert response.status_code == 201
    data = client.post(
        "/forecast",
        json={
            "dataset_id": response.json()["dataset_id"],
            "store_id": "S1",
            "product_id": "P1",
            "horizon": horizon,
        },
    )
    assert data.status_code == 200, data.text
    assert len(data.json()["forecast"]) == horizon


def test_analytics_filters_and_actual_aggregations(client, series):
    dataset = upload(client, series).json()["dataset_id"]
    response = client.get(
        f"/analytics/{dataset}?store=S1&product=P1&date_from=2025-01-01&date_to=2025-01-07"
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_units"] == series.units_sold.head(7).sum()
    assert data["total_revenue"] == (series.units_sold * series.price).head(7).sum()
    assert len(data["weekday_pattern"]) == 7
    assert len(data["sales_over_time"]) == 7
    assert data["sales_by_category"] == []
    assert client.get(f"/analytics/{dataset}?store=missing").status_code == 404
    assert (
        client.get(f"/analytics/{dataset}?date_from=2026-01-01&date_to=2025-01-01").status_code
        == 422
    )


@pytest.mark.parametrize(
    "filename,body,status",
    [
        ("file.txt", b"not csv", 415),
        ("sales.csv", b"", 422),
        ("sales.csv", b"date,store_id\n2025-01-01,S1", 422),
        ("sales.csv", b"date,store_id,product_id,units_sold,price\nbad,S1,P1,-1,0", 422),
        ("sales.csv", b'date,store_id\n"bad', 422),
    ],
)
def test_upload_errors_are_meaningful(client, filename, body, status):
    response = client.post("/datasets/upload", files={"file": (filename, body, "text/csv")})
    assert response.status_code == status
    assert response.json()["error"]


@pytest.mark.parametrize(
    "field,value,status",
    [
        ("store_id", "missing", 404),
        ("product_id", "missing", 404),
        ("horizon", 10, 422),
        ("missing_policy", "automatic", 422),
    ],
)
def test_invalid_forecast_request(client, series, field, value, status):
    dataset_id = upload(client, series).json()["dataset_id"]
    payload = {
        "dataset_id": dataset_id,
        "store_id": "S1",
        "product_id": "P1",
        "horizon": 7,
        field: value,
    }
    response = client.post("/forecast", json=payload)
    assert response.status_code == status
    assert response.json()["error"]


def test_insufficient_history_returns_actionable_error(client, series):
    dataset_id = upload(client, series.head(18)).json()["dataset_id"]
    response = client.post(
        "/forecast",
        json={"dataset_id": dataset_id, "store_id": "S1", "product_id": "P1", "horizon": 7},
    )
    assert response.status_code == 422
    assert "90" in response.json()["error"]


def test_missing_dates_require_explicit_zero_policy(client, series):
    dataset_id = upload(client, series.drop(index=50)).json()["dataset_id"]
    payload = {"dataset_id": dataset_id, "store_id": "S1", "product_id": "P1", "horizon": 7}
    refused = client.post("/forecast", json=payload)
    assert refused.status_code == 422
    assert "missing sales" in refused.json()["error"]
    accepted = client.post("/forecast", json={**payload, "missing_policy": "zero"})
    assert accepted.status_code == 200, accepted.text
    assert "1 missing" in accepted.json()["warnings"][0]
    assert accepted.json()["missing_policy"] == "zero"


def test_inventory_gap_requires_latest_observation(client, series):
    series["inventory"] = 100
    series.loc[len(series) - 1, "inventory"] = float("nan")
    dataset_id = upload(client, series).json()["dataset_id"]
    response = client.post(
        "/forecast",
        json={"dataset_id": dataset_id, "store_id": "S1", "product_id": "P1", "horizon": 7},
    )
    assert response.status_code == 200
    assert response.json()["summary"]["current_inventory"] is None
    assert response.json()["summary"]["inventory_gap"] is None


def test_model_failure_is_a_controlled_api_error(client, series, monkeypatch):
    def failure(*args, **kwargs):
        raise ValueError("internal numerical details")

    monkeypatch.setattr("backend.app.forecasting.predictor.train_baselines", failure)
    dataset_id = upload(client, series).json()["dataset_id"]
    response = client.post(
        "/forecast",
        json={"dataset_id": dataset_id, "store_id": "S1", "product_id": "P1", "horizon": 7},
    )
    assert response.status_code == 422
    assert "could not be fitted" in response.json()["error"]
    assert "internal numerical" not in response.text


def test_unknown_dataset_and_run(client):
    assert client.get("/datasets/missing").status_code == 404
    assert client.get("/forecasts/missing").status_code == 404
    assert client.get("/health").json()["status"] == "ok"


def test_optional_columns_survive_ingestion(client, series):
    series["category"] = "123"
    dataset_id = upload(client, series).json()["dataset_id"]
    response = client.get(f"/datasets/{dataset_id}/options")
    assert response.status_code == 200
    assert response.json()["categories"] == ["123"]


def test_unknown_sales_are_not_displayed_as_zero(client, series):
    series.loc[:6, "units_sold"] = float("nan")
    dataset_id = upload(client, series).json()["dataset_id"]
    response = client.get(f"/analytics/{dataset_id}?date_to=2025-01-07")
    assert response.status_code == 200
    data = response.json()
    assert data["total_units"] is None
    assert data["average_daily_units"] is None
    assert all(point["units"] is None for point in data["sales_over_time"])
