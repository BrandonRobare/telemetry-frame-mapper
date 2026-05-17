from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client(setup_test_db):
    with TestClient(app) as c:
        yield c


def test_get_storage_summary_shape(client):
    resp = client.get("/storage/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_bytes" in data
    assert "by_type" in data
    assert "by_session" in data
    for key in ["imports", "processed", "exports", "data"]:
        assert key in data["by_type"]
        assert isinstance(data["by_type"][key], int)


def test_get_storage_summary_total_is_sum_of_parts(client):
    resp = client.get("/storage/summary")
    data = resp.json()
    parts_sum = sum(data["by_type"].values())
    assert data["total_bytes"] == parts_sum


def test_get_storage_summary_returns_list_for_by_session(client):
    resp = client.get("/storage/summary")
    assert isinstance(resp.json()["by_session"], list)
