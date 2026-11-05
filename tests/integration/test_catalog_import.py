import copy
import json
import shutil
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.app.data.repository import load_dataset
from backend.app.db.models import AdvancedRun
from backend.app.errors import AppError
from backend.app.schemas.advanced import TrainingRequest
from backend.app.services.advanced_training import train_advanced
from backend.app.services.catalog_import import import_catalog


@pytest.fixture
def catalog(client, series, tmp_path):
    uploaded = client.post(
        "/datasets/upload", files={"file": ("sales.csv", series.to_csv(index=False))}
    )
    assert uploaded.status_code == 201, uploaded.text
    dataset_id = uploaded.json()["dataset_id"]
    storage = client.app.state.storage
    source = tmp_path / "catalog"
    (source / "runs").mkdir(parents=True)
    with client.app.state.session_factory() as session:
        frame = load_dataset(dataset_id, session, storage)
    request = TrainingRequest(
        dataset_id="original-offline-dataset",
        store_id="S1",
        product_id="P1",
        horizon=7,
        folds=2,
        models=["naive"],
        tune=False,
    )
    run_id = str(uuid4())
    result = train_advanced(frame, request, run_id, source / "artifacts" / run_id)
    (source / "runs" / "000.json").write_text(json.dumps(result, allow_nan=False))
    return source, dataset_id, result


def invoke(client, catalog, **kwargs):
    source, dataset_id, _ = catalog
    with client.app.state.session_factory() as session:
        return import_catalog(session, client.app.state.storage, source, dataset_id, **kwargs)


def test_catalog_dry_run_import_reload_and_idempotency(client, catalog, monkeypatch):
    source, dataset_id, original = catalog
    # Registration must neither deserialize nor retrain; predictions deserialize afterwards.
    with monkeypatch.context() as guard:
        guard.setattr("joblib.load", lambda *_: pytest.fail("Import must not unpickle"))
        assert invoke(client, catalog, dry_run=True)["validated"] == 1
        assert client.get("/forecast/models").json() == []
        assert not (client.app.state.storage / "artifacts").exists()
        assert invoke(client, catalog)["imported"] == 1
        assert invoke(client, catalog)["skipped"] == 1
    run_id = original["run_id"]
    detail = client.get(f"/forecast/runs/{run_id}").json()
    assert detail["dataset_id"] == dataset_id
    assert detail["configuration"]["dataset_id"] == dataset_id
    assert detail["catalog_import"]["source_dataset_id"] == "original-offline-dataset"
    assert json.loads((source / "runs" / "000.json").read_text()) == original
    predicted = client.post("/forecast/predict", json={"run_id": run_id})
    assert predicted.status_code == 200, predicted.text
    assert predicted.json()["forecast"] == original["forecast"]
    assert (
        client.get("/forecast/model-comparison", params={"run_id": run_id}).json()
        == original["comparison"]
    )
    plan = client.post(
        "/inventory/optimize",
        json={"forecast_run_id": run_id, "on_hand_inventory": 0, "lead_time": 2},
    )
    assert plan.status_code == 201, plan.text
    assert plan.json()["expedite_needed"] is True
    assert (
        client.get("/inventory/kpis", params={"dataset_id": dataset_id}).json()["series_count"]
        == 1
    )


@pytest.mark.parametrize(
    "damage", ["artifact", "history", "quantiles", "calibration", "timestamp", "conflict"]
)
def test_rejects_bad_catalog_and_rolls_back_entire_batch(client, catalog, damage):
    source, dataset_id, original = catalog
    second = copy.deepcopy(original)
    second["run_id"] = str(uuid4())
    directory = source / "artifacts" / second["run_id"]
    shutil.copytree(source / "artifacts" / original["run_id"], directory)
    if damage == "artifact":
        (directory / "calibrator.joblib").write_bytes(b"corrupted")
    elif damage == "history":
        second["history"][0]["actual"] += 1
    elif damage == "quantiles":
        second["forecast"][0]["p10"] = second["forecast"][0]["p90"] + 1
    elif damage == "calibration":
        second["calibration"]["records"][0]["training_end"] = "2099-01-01"
    elif damage == "timestamp":
        second["created_at"] = "2026-01-01"
    else:
        with client.app.state.session_factory() as session:
            session.add(
                AdvancedRun(
                    id=second["run_id"],
                    dataset_id=dataset_id,
                    champion_model=second["champion_model"],
                    configuration={},
                    result={},
                )
            )
            session.commit()
    (source / "runs" / "001.json").write_text(json.dumps(second))
    with pytest.raises(AppError, match="Catalog import rejected at 001.json"):
        invoke(client, catalog)
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AdvancedRun)) == (
            1 if damage == "conflict" else 0
        )
    assert not (client.app.state.storage / "artifacts" / original["run_id"]).exists()
    assert not (client.app.state.storage / "artifacts" / second["run_id"]).exists()
    assert (source / "artifacts" / original["run_id"] / "calibrator.joblib").exists()


def test_existing_import_requires_intact_target_artifacts(client, catalog):
    invoke(client, catalog)
    run_id = catalog[2]["run_id"]
    (client.app.state.storage / "artifacts" / run_id / "calibrator.joblib").write_bytes(b"damaged")
    with pytest.raises(AppError, match="missing or damaged"):
        invoke(client, catalog)
    assert client.get(f"/forecast/runs/{run_id}").status_code == 200


def test_model_pagination_has_stable_ties_and_dataset_filter(client, catalog):
    invoke(client, catalog)
    _, dataset_id, original = catalog
    with client.app.state.session_factory() as session:
        saved = session.get(AdvancedRun, original["run_id"])
        for _ in range(100):
            session.add(
                AdvancedRun(
                    id=str(uuid4()),
                    dataset_id=dataset_id,
                    champion_model=saved.champion_model,
                    created_at=saved.created_at,
                    configuration=saved.configuration,
                    result=saved.result,
                )
            )
        session.commit()
    pages = [
        client.get("/forecast/models", params={"dataset_id": dataset_id, "offset": n}).json()
        for n in (0, 100, 200)
    ]
    assert [len(p) for p in pages] == [100, 1, 0]
    ids = [r["run_id"] for page in pages for r in page]
    assert len(set(ids)) == 101
    assert ids == sorted(ids, reverse=True)
    assert client.get("/forecast/models", params={"dataset_id": "different"}).json() == []
    assert client.get("/forecast/models?limit=501").status_code == 422
    assert client.get("/forecast/models?offset=-1").status_code == 422
