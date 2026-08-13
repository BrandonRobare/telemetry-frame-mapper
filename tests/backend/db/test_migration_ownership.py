from pathlib import Path

MIGRATION = Path("backend/db/migrations/versions/0001_baseline.py").read_text()


def test_baseline_leaves_flight_log_sync_columns_to_revision_0002() -> None:
    assert "_IMAGE_FLIGHT_LOG_SYNC_COLUMNS" not in MIGRATION
    assert "original_latitude" not in MIGRATION
    assert "synced_altitude_m" not in MIGRATION


def test_baseline_documents_shim_column_owner_convention() -> None:
    assert "Columns introduced by a numbered revision belong only" in MIGRATION
