from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy.exc import SQLAlchemyError


def test_metrics_uses_prometheus_text_format(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert 'drone_mapping_build_info{version="1.0.0"} 1' in response.text
    assert "drone_mapping_process_start_time_seconds " in response.text
    assert "drone_mapping_database_up 1" in response.text


def test_metrics_reports_database_probe_failure(client, monkeypatch):
    session = MagicMock()
    session.execute.side_effect = SQLAlchemyError("unavailable")

    def failed_db():
        yield session

    from backend.db.database import get_db
    from backend.main import app

    original_db = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = failed_db
    try:
        response = client.get("/metrics")
    finally:
        app.dependency_overrides[get_db] = original_db

    assert response.status_code == 200
    assert "drone_mapping_database_up 0" in response.text
    assert client.get("/sessions").status_code == 200
