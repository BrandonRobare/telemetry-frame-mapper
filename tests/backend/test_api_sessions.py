from __future__ import annotations


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_tables_created(client, db_engine):
    from sqlalchemy import inspect

    inspector = inspect(db_engine)
    tables = inspector.get_table_names()
    for expected in [
        "sessions",
        "images",
        "footprints",
        "flight_logs",
        "flight_log_points",
        "target_areas",
        "coverage_runs",
        "mission_plans",
        "session_log_entries",
    ]:
        assert expected in tables, f"Missing table: {expected}"
