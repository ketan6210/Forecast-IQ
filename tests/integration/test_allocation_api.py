import csv
import io

import pytest
from sqlalchemy import func, select

from backend.app.db.models import InventoryAllocation


@pytest.fixture
def allocation_plans(client):
    dataset = client.post("/datasets/demo").json()["dataset_id"]
    plans = []
    for sku in ["SKU_001", "SKU_002"]:
        run = client.post(
            "/forecast/train",
            json={
                "dataset_id": dataset,
                "store_id": "STORE_01",
                "product_id": sku,
                "horizon": 7,
                "folds": 2,
                "models": ["naive"],
                "tune": False,
            },
        ).json()
        response = client.post(
            "/inventory/optimize",
            json={
                "forecast_run_id": run["run_id"],
                "on_hand_inventory": 0,
                "lead_time": 2,
                "unit_cost": 3,
                "currency": "USD",
                "minimum_order_quantity": 6,
                "order_multiple": 3,
            },
        )
        assert response.status_code == 201, response.text
        plans.append(response.json())
    return dataset, plans


def test_allocate_persist_restore_export_and_original_plans_unchanged(client, allocation_plans):
    dataset, plans = allocation_plans
    response = client.post(
        "/inventory/allocate",
        json={
            "dataset_id": dataset,
            "items": [
                {"plan_id": p["plan_id"], "capacity_per_unit": 2, "priority_weight": i + 1}
                for i, p in enumerate(plans)
            ],
            "purchasing_budget": 36,
            "available_capacity": 18,
            "capacity_unit": "m3",
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["purchase_cost"] == 27
    assert result["capacity_used"] == 18
    assert [i["allocated_quantity"] for i in result["items"]] == [0, 9]
    path = f"/inventory/allocations/{result['allocation_id']}"
    assert client.get(path).json() == result
    listed = client.get("/inventory/allocations", params={"dataset_id": dataset}).json()
    assert listed[0]["allocation_id"] == result["allocation_id"]
    assert client.get("/inventory/allocations?dataset_id=unrelated").json() == []
    exported = list(csv.DictReader(io.StringIO(client.get(path + "/export").text)))
    assert len(exported) == 2 and float(exported[1]["allocated_quantity"]) == 9
    for p in plans:
        assert (
            client.get(f"/inventory/plans/{p['plan_id']}").json()["recommended_order_quantity"]
            == p["recommended_order_quantity"]
        )


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"purchasing_budget": -1},
        {"available_capacity": 10},
        {"available_capacity": 10, "capacity_unit": "m3"},
        {"purchasing_budget": "NaN"},
    ],
)
def test_invalid_resources_do_not_save(client, allocation_plans, extra):
    dataset, plans = allocation_plans
    result = client.post(
        "/inventory/allocate",
        json={"dataset_id": dataset, "items": [{"plan_id": p["plan_id"]} for p in plans], **extra},
    )
    assert result.status_code == 422
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(InventoryAllocation)) == 0


def test_unknown_and_cross_dataset_plans_do_not_save(client, allocation_plans):
    _, plans = allocation_plans
    for dataset, plan_id, code in [
        ("missing", "missing", 404),
        ("other", plans[0]["plan_id"], 422),
    ]:
        response = client.post(
            "/inventory/allocate",
            json={"dataset_id": dataset, "items": [{"plan_id": plan_id}], "purchasing_budget": 5},
        )
        assert response.status_code == code, response.text
    assert client.get("/inventory/allocations/missing").status_code == 404
