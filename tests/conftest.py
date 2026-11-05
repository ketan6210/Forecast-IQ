from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


@pytest.fixture
def series() -> pd.DataFrame:
    days = np.arange(140)
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=len(days)),
            "store_id": "S1",
            "product_id": "P1",
            "units_sold": 20 + days % 7 + (days // 7) % 3,
            "price": 10 + (days % 30 == 0).astype(float),
            "promotion": (days % 15 == 0).astype(int),
        }
    )


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}", tmp_path / "datasets")
    with TestClient(app) as test_client:
        yield test_client
