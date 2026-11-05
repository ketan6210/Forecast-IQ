import csv
import io

import pytest
from sqlalchemy import create_engine, inspect, select, text

from backend.app.db.migrations import migrate_database
from backend.app.db.models import AdvancedRun, Base, Dataset, ForecastRun


@pytest.fixture
def saved(client):
    dataset = client.post("/datasets/demo").json()["dataset_id"]
    response = client.post(
        "/forecast/train",
        json={
            "dataset_id": dataset,
            "store_id": "STORE_01",
            "product_id": "SKU_001",
            "horizon": 30,
            "folds": 2,
            "models": ["naive", "seasonal_naive"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def body(saved, **changes):
    return {
        "forecast_run_id": saved["run_id"],
        "on_hand_inventory": 150,
        "lead_time": 7,
        "annual_demand": 12000,
        "ordering_cost": 20,
        "holding_cost_per_unit_per_year": 3,
        "stockout_cost": 8,
        "unit_cost": 12,
        "currency": "USD",
        **changes,
    }


def test_late_supply_appears_in_risk_priority_kpis_export_and_simulation(client, saved):
    config = body(
        saved,
        on_hand_inventory=0,
        on_order_inventory=100000,
        lead_time=2,
        incoming_orders=[{"period": 20, "quantity": 100000}],
    )
    early = client.post(
        "/inventory/optimize",
        json={
            **config,
            "warehouse_id": "EARLY",
            "incoming_orders": [{"period": 1, "quantity": 100000}],
        },
    ).json()
    response = client.post("/inventory/optimize", json={**config, "warehouse_id": "LATE"})
    assert response.status_code == 201, response.text
    late = response.json()
    assert late["recommended_order_quantity"] == 0
    assert late["inventory_position"] == 100000
    assert late["risk_level"] == "high"
    assert late["expedite_quantity"] > 0
    assert early["risk_level"] == "low"
    params = {"dataset_id": saved["dataset_id"]}
    queue = client.get("/inventory/recommendations", params=params).json()
    assert [row["plan_id"] for row in queue["items"]] == [late["plan_id"], early["plan_id"]]
    portfolio = client.get("/inventory/kpis", params=params).json()
    assert portfolio["high_risk_series"] == portfolio["expedite_needed"] == 1
    assert portfolio["plans_requiring_recalculation"] == 0
    exported = list(
        csv.DictReader(io.StringIO(client.get("/inventory/export", params=params).text))
    )
    assert all("expedite_quantity" in row for row in exported)
    simulation = client.post(
        "/inventory/simulate",
        json={"plan_id": late["plan_id"], "mode": "deterministic", "horizon": 7},
    ).json()
    assert simulation["fill_rate"] == 0
    assert simulation["expected_lost_units"] == pytest.approx(
        sum(p["p50"] for p in saved["forecast"][:7])
    )


def test_end_to_end_persisted_forecast_inventory_simulation_scenario_api(
    client, saved, monkeypatch
):
    # Any training call during inventory/scenario work would fail this test.
    def forbidden(*args, **kwargs):
        raise AssertionError("Inventory must use the saved forecast")

    monkeypatch.setattr("backend.app.api.advanced.train_advanced", forbidden)
    response = client.post("/inventory/optimize", json=body(saved, order_multiple=12))
    assert response.status_code == 201, response.text
    plan = response.json()
    assert plan["expected_lead_time_demand"] == pytest.approx(
        sum(p["p50"] for p in saved["forecast"][:7])
    )
    assert plan["recommended_order_quantity"] % 12 == 0
    assert plan["eoq"] == 400
    assert plan["forecast_run_id"] == saved["run_id"]
    assert len(plan["calculation_details"]) >= 4
    deterministic = client.post(
        "/inventory/simulate", json={"plan_id": plan["plan_id"], "mode": "deterministic"}
    )
    assert deterministic.status_code == 201, deterministic.text
    assert deterministic.json()["paths"] == 1
    config = {"plan_id": plan["plan_id"], "trials": 100, "seed": 27}
    mc = client.post("/inventory/simulate", json=config).json()
    again = client.post("/inventory/simulate", json=config).json()
    assert mc["trajectory"] == again["trajectory"]
    assert mc["expected_total_cost"] == again["expected_total_cost"]
    assert mc["cost_distribution"]["p10"] <= mc["cost_distribution"]["p90"]
    comparison = client.post(
        "/inventory/policy-comparison", json={**config, "minimum_fill_rate": 0.5}
    )
    assert comparison.status_code == 201, comparison.text
    assert len(comparison.json()["service_level_comparison"]) == 4
    assert (
        client.get("/inventory/policy-comparison", params={"plan_id": plan["plan_id"]}).json()
        == comparison.json()
    )
    scenario = client.post(
        "/inventory/scenario",
        json={
            **config,
            "horizon": 20,
            "changes": {"lead_time": 3, "service_level": 0.99, "on_hand_inventory": 500},
        },
    )
    assert scenario.status_code == 201, scenario.text
    changed = scenario.json()["scenario"]["recommendation"]
    assert changed["inventory_position"] == 500
    assert changed["expected_lead_time_demand"] < plan["expected_lead_time_demand"]
    assert scenario.json()["scenario"]["simulation"]["horizon"] == 20
    detail = client.get(f"/inventory/plans/{plan['plan_id']}").json()
    assert detail["inputs"]["lead_time"] == 7
    assert detail["latest_simulation"]["analysis_id"] == again["analysis_id"]
    kpi = client.get("/inventory/kpis", params={"dataset_id": saved["dataset_id"]}).json()
    assert kpi["series_count"] == 1
    assert kpi["expected_total_cost"] == pytest.approx(mc["expected_total_cost"])
    assert kpi["total_inventory_value"] == 1800
    assert kpi["abc_distribution"] == {"A": 1}
    assert client.get("/inventory/sku/SKU_001", params={"dataset_id": saved["dataset_id"]}).json()[
        "items"
    ]


def test_multi_location_batch_latest_pagination_filters_csv_and_segments(client, saved):
    request = body(saved)
    result = client.post(
        "/inventory/batch",
        json={
            "items": [
                request,
                {**request, "warehouse_id": "WEST", "on_hand_inventory": 9999},
                {**request, "forecast_run_id": "missing"},
            ]
        },
    ).json()
    assert result["successful"] == 2 and result["failed"] == 1
    latest = client.post("/inventory/optimize", json={**request, "on_hand_inventory": 100}).json()
    params = {"dataset_id": saved["dataset_id"]}
    all_rows = client.get(
        "/inventory/recommendations", params={**params, "sort": "sku", "limit": 1}
    ).json()
    assert all_rows["total"] == 2 and len(all_rows["items"]) == 1
    risk = client.get("/inventory/recommendations", params={**params, "risk": "high"}).json()
    assert all(r["risk_level"] == "high" for r in risk["items"])
    search = client.get("/inventory/recommendations", params={**params, "search": "WEST"}).json()
    assert search["total"] == 1
    below = client.get("/inventory/recommendations", params={**params, "reorder_only": True}).json()
    assert below["items"][0]["plan_id"] == latest["plan_id"]
    export = client.get("/inventory/export", params=params)
    rows = list(csv.DictReader(io.StringIO(export.text)))
    assert len(rows) == 2
    assert {r["location_id"] for r in rows} == {"WEST", "STORE_01"}
    assert "stockout_risk" in rows[0] and "on_hand_inventory" in rows[0]
    abc = client.get("/inventory/abc-analysis", params=params).json()
    assert len(abc["items"]) == 2
    assert abc["items"][0]["xyz_class"] in {"X", "Y", "Z"}
    custom = client.post(
        "/inventory/abc-analysis", json={**params, "a_threshold": 0.7, "b_threshold": 0.9}
    )
    assert custom.json()["thresholds"]["a"] == 0.7
    assert (
        client.post(
            "/inventory/abc-analysis", json={**params, "a_threshold": 0.9, "b_threshold": 0.8}
        ).status_code
        == 422
    )
    csv_data = (
        "forecast_run_id,on_hand_inventory,lead_time,warehouse_id\n"
        f"{saved['run_id']},40,2,EAST\nmissing,0,1,NONE\n"
    )
    imported = client.post(
        "/inventory/import", files={"file": ("inventory.csv", csv_data, "text/csv")}
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["successful"] == 1 and imported.json()["failed"] == 1


def test_api_invalid_inputs_absent_runs_and_schedule(client, saved):
    assert (
        client.post(
            "/inventory/optimize",
            json={"forecast_run_id": "none", "on_hand_inventory": 0, "lead_time": 1},
        ).status_code
        == 404
    )
    assert client.post("/inventory/optimize", json=body(saved, lead_time=50)).status_code == 422
    assert client.post("/inventory/optimize", json=body(saved, unit_cost=-1)).status_code == 422
    assert (
        client.post("/inventory/optimize", json={"forecast_run_id": saved["run_id"]}).status_code
        == 422
    )
    plan = client.post("/inventory/optimize", json=body(saved, on_order_inventory=50)).json()
    response = client.post("/inventory/simulate", json={"plan_id": plan["plan_id"]})
    assert response.status_code == 422 and "arrival periods" in response.text
    assert client.post("/inventory/simulate", json={"plan_id": "missing"}).status_code == 404
    assert (
        client.post(
            "/inventory/scenario", json={"plan_id": plan["plan_id"], "changes": {"lead_time": -1}}
        ).status_code
        == 422
    )
    assert (
        client.get("/inventory/policy-comparison", params={"plan_id": plan["plan_id"]}).status_code
        == 404
    )
    assert (
        client.post("/inventory/import", files={"file": ("bad.csv", "a,b\n1,2")}).status_code == 422
    )
    assert (
        client.post("/inventory/import", files={"file": ("big.csv", b"x" * 2_000_001)}).status_code
        == 413
    )


def test_migration_adopts_populated_phase2_database_and_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    Base.metadata.create_all(
        engine, tables=[Dataset.__table__, ForecastRun.__table__, AdvancedRun.__table__]
    )
    with engine.begin() as conn:
        conn.execute(
            Dataset.__table__.insert().values(
                id="legacy", filename="old.csv", is_demo=False, report={}, timings={}
            )
        )
    migrate_database(engine)
    migrate_database(engine)
    assert {
        "datasets",
        "forecast_runs",
        "advanced_runs",
        "inventory_plans",
        "inventory_simulations",
    } <= set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        assert conn.scalar(select(Dataset.filename)) == "old.csv"
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0002_inventory"
    engine.dispose()
