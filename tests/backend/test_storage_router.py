from __future__ import annotations

from unittest.mock import patch


def test_storage_summary_fields(client):
    with patch("backend.routers.storage._compute_summary") as mock_summary:
        mock_summary.return_value = {
            "total_bytes": 1_000_000,
            "by_type": {"frames": 500_000, "exports": 500_000},
            "by_session": [],
        }
        resp = client.get("/storage/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert "total_bytes" in data
    assert "by_type" in data


def test_storage_summary_cached(client):
    with patch("backend.routers.storage._compute_summary") as mock_summary:
        mock_summary.return_value = {"total_bytes": 0, "by_type": {}, "by_session": []}
        client.get("/storage/summary")
        client.get("/storage/summary")
        assert mock_summary.call_count <= 2
