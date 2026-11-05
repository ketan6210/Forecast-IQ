import numpy as np
import pandas as pd
import pytest


def upload(client, frame, **options):
    response = client.post(
        "/datasets/upload",
        files={"file": ("demand.csv", frame.to_csv(index=False), "text/csv")},
        data=options,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "options",
    [
        {},
        {
            "date_column": "date",
            "target_column": "units_sold",
            "store_column": "store_id",
            "product_column": "product_id",
            "price_column": "price",
        },
    ],
)
def test_kaggle_sales_upload_with_defaults_can_be_forecast(client, series, options):
    frame = series[["date", "units_sold"]].rename(columns={"units_sold": "sales"})
    frame["store"] = "001"
    frame["item"] = "002"
    data = upload(client, frame, **options)
    assert data["processed_row_count"] == len(frame)
    assert data["column_mapping"]["units_sold"] == "sales"
    assert data["column_mapping"]["store_id"] == "store"
    assert data["column_mapping"]["product_id"] == "item"
    saved_options = client.get(f"/datasets/{data['dataset_id']}/options").json()
    assert saved_options["store_products"] == {"001": ["002"]}
    analytics = client.get(f"/analytics/{data['dataset_id']}").json()
    assert analytics["total_units"] == float(frame.sales.sum())
    assert analytics["total_revenue"] is None
    forecast = client.post(
        "/forecast",
        json={
            "dataset_id": data["dataset_id"],
            "store_id": "001",
            "product_id": "002",
            "horizon": 7,
        },
    )
    assert forecast.status_code == 200, forecast.text
    assert len(forecast.json()["forecast"]) == 7


def test_kaggle_aliases_do_not_override_canonical_columns(client, series):
    series["store"] = "OTHER_STORE"
    series["item"] = "OTHER_ITEM"
    series["sales"] = 999999
    data = upload(client, series)
    options = client.get(f"/datasets/{data['dataset_id']}/options").json()
    assert options["store_products"] == {"S1": ["P1"]}
    analytics = client.get(f"/analytics/{data['dataset_id']}").json()
    assert analytics["total_units"] == float(series.units_sold.sum())


def test_kaggle_aliases_respect_explicit_target_mapping(client, series):
    frame = series.rename(
        columns={"store_id": "store", "product_id": "item", "units_sold": "sales"}
    )
    frame["observed_demand"] = frame.sales * 2
    data = upload(client, frame, target_column="observed_demand")
    assert data["column_mapping"]["units_sold"] == "observed_demand"
    analytics = client.get(f"/analytics/{data['dataset_id']}").json()
    assert analytics["total_units"] == float(frame.observed_demand.sum())
    invalid = client.post(
        "/datasets/upload",
        files={"file": ("sales.csv", frame.to_csv(index=False), "text/csv")},
        data={"target_column": "unknown"},
    )
    assert invalid.status_code == 422
    assert "Cannot map unknown" in invalid.json()["error"]


def test_kaggle_test_rows_without_sales_are_not_training_data(client, series):
    frame = series[["date", "store_id", "product_id"]].rename(
        columns={"store_id": "store", "product_id": "item"}
    )
    frame["id"] = np.arange(len(frame))
    response = client.post(
        "/datasets/upload",
        files={"file": ("test.csv", frame.to_csv(index=False), "text/csv")},
    )
    assert response.status_code == 422
    assert "upload train.csv" in response.json()["error"]
    assert "test.csv only lists rows to forecast" in response.json()["error"]
    assert client.get("/datasets").json() == []


def test_kaggle_submission_template_explains_which_file_to_upload(client):
    response = client.post(
        "/datasets/upload",
        files={"file": ("sample_submission.csv", "id,sales\n0,52\n1,52\n", "text/csv")},
    )
    assert response.status_code == 422
    assert "upload train.csv" in response.json()["error"]
    assert "output template, not training data" in response.json()["error"]
    assert client.get("/datasets").json() == []


def test_price_free_mapped_series_predictors_training_shap_and_inventory(client, series):
    frame = series.drop(columns=["price", "store_id", "product_id"])
    frame["temperature"] = np.arange(len(frame), dtype=float) % 30
    frame = frame.rename(columns={"date": "period", "units_sold": "demand"})
    data = upload(
        client,
        frame,
        date_column="period",
        target_column="demand",
        store_column="__single__",
        product_column="__single__",
        external_features="temperature",
    )
    assert data["external_features"] == ["temperature"]
    assert client.get(f"/datasets/{data['dataset_id']}").json()["external_features"] == [
        "temperature"
    ]
    eda = client.get(f"/analytics/{data['dataset_id']}").json()
    assert eda["total_revenue"] is None
    assert eda["demand_statistics"]["median"] == float(frame.demand.median())
    config = {
        "dataset_id": data["dataset_id"],
        "store_id": "ALL_STORES",
        "product_id": "ALL_PRODUCTS",
        "horizon": 7,
    }
    legacy = client.post("/forecast", json=config)
    assert legacy.status_code == 200, legacy.text
    response = client.post(
        "/forecast/train",
        json={
            **config,
            "folds": 2,
            "tuning_trials": 3,
            "tuning_seed": 17,
            "models": ["linear_regression", "lightgbm", "xgboost"],
        },
    )
    assert response.status_code == 201, response.text
    run = response.json()
    for name in ("lightgbm", "xgboost"):
        row = next(r for r in run["comparison"] if r["model"] == name)
        assert row["status"] == "ok"
        assert len(row["trials"]) == 3
        assert row["tuning_seed"] == 17
        assert row["search_method"] == "seeded_randomized_chronological"
        assert "temperature" in run["artifacts"][name]["features"]
        assert "temperature" in {
            r["feature"] for r in run["explainability"][name]["global_importance"]
        }
    loaded = client.post("/forecast/predict", json={"run_id": run["run_id"]})
    assert loaded.status_code == 200
    assert loaded.json()["forecast"] == run["forecast"]
    plan = client.post(
        "/inventory/optimize",
        json={"forecast_run_id": run["run_id"], "on_hand_inventory": 50, "lead_time": 2},
    )
    assert plan.status_code == 201
    assert plan.json()["inventory_value"] is None
    assert plan.json()["eoq"] is None


@pytest.mark.parametrize("frequency", ["W-MON", "MS", "ME"])
def test_eda_date_filters_preserve_declared_frequency(client, series, frequency):
    series.date = pd.date_range("2015-01-01", periods=len(series), freq=frequency)
    data = upload(client, series)
    response = client.get(
        f"/analytics/{data['dataset_id']}",
        params={
            "date_from": str(series.date.iloc[3].date()),
            "date_to": str(series.date.iloc[4].date()),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["frequency"] == frequency
    assert len(response.json()["sales_over_time"]) == 2


def test_explicit_daily_frequency_is_used_by_auto_training(client, series):
    series.date = pd.date_range("2023-01-02", periods=len(series), freq="W-MON")
    data = upload(client, series, frequency="daily")
    run = client.post(
        "/forecast/train",
        json={
            "dataset_id": data["dataset_id"],
            "store_id": "S1",
            "product_id": "P1",
            "horizon": 7,
            "folds": 2,
            "models": ["naive"],
            "missing_policy": "zero",
        },
    )
    assert run.status_code == 201, run.text
    assert run.json()["frequency"] == "D"
    dates = pd.to_datetime([p["date"] for p in run.json()["forecast"]])
    assert (np.diff(dates.values) == np.timedelta64(1, "D")).all()


def test_price_column_mapping(client, series):
    data = upload(client, series.rename(columns={"price": "amount"}), price_column="amount")
    result = client.get(f"/analytics/{data['dataset_id']}").json()
    assert result["total_revenue"] == pytest.approx(float((series.price * series.units_sold).sum()))


def test_unknown_non_numeric_and_duplicate_predictors_are_actionable(client, series):
    series["weather"] = "sunny"
    for predictors in ("weather", "unknown", "promotion", "price,price"):
        response = client.post(
            "/datasets/upload",
            files={"file": ("d.csv", series.to_csv(index=False), "text/csv")},
            data={"external_features": predictors},
        )
        assert response.status_code == 422, response.text


def test_scenario_horizon_recalculates_recommendations_without_mutating_plan(client, series):
    data = upload(client, series)
    run = client.post(
        "/forecast/train",
        json={
            "dataset_id": data["dataset_id"],
            "store_id": "S1",
            "product_id": "P1",
            "horizon": 14,
            "folds": 2,
            "models": ["naive"],
        },
    ).json()
    plan = client.post(
        "/inventory/optimize",
        json={
            "forecast_run_id": run["run_id"],
            "on_hand_inventory": 50,
            "lead_time": 2,
            "annualize_forecast": True,
        },
    ).json()
    scenario = client.post(
        "/inventory/scenario",
        json={"plan_id": plan["plan_id"], "horizon": 5, "trials": 100, "changes": {"lead_time": 3}},
    )
    assert scenario.status_code == 201, scenario.text
    for name in ("baseline", "scenario"):
        r = scenario.json()[name]["recommendation"]
        assert r["forecast_horizon"] == 5
        assert len(r["forecast"]) == 5
        assert r["forecast_p50_total"] == pytest.approx(sum(p["p50"] for p in run["forecast"][:5]))
    assert client.get(f"/inventory/plans/{plan['plan_id']}").json()["forecast_horizon"] == 14
    assert (
        client.post(
            "/inventory/scenario", json={"plan_id": plan["plan_id"], "horizon": 15, "changes": {}}
        ).status_code
        == 422
    )


def test_portfolio_cannot_combine_different_shortage_modes(client, series):
    data = upload(client, series)
    run = client.post(
        "/forecast/train",
        json={
            "dataset_id": data["dataset_id"],
            "store_id": "S1",
            "product_id": "P1",
            "horizon": 7,
            "folds": 2,
            "models": ["naive"],
        },
    ).json()
    for index, mode in enumerate(("lost_sales", "backorders")):
        plan = client.post(
            "/inventory/optimize",
            json={
                "forecast_run_id": run["run_id"],
                "warehouse_id": str(index),
                "on_hand_inventory": 10,
                "lead_time": 2,
                "holding_cost_per_unit_per_year": 2,
                "ordering_cost": 3,
                "stockout_cost": 4,
            },
        ).json()
        response = client.post(
            "/inventory/simulate",
            json={"plan_id": plan["plan_id"], "trials": 100, "shortage_mode": mode},
        )
        assert response.status_code == 201
    kpis = client.get("/inventory/kpis", params={"dataset_id": data["dataset_id"]}).json()
    assert kpis["simulated_series_count"] == 2
    assert kpis["expected_total_cost"] is None
    assert kpis["fill_rate"] is None
