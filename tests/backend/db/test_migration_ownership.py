import ast
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

BASELINE_PATH = Path("backend/db/migrations/versions/0001_baseline.py")
MIGRATION = BASELINE_PATH.read_text()

# Owned by revision 0002, which adds them to legacy databases itself.
_FLIGHT_LOG_SYNC_COLUMNS = {
    "original_latitude",
    "original_longitude",
    "original_altitude_m",
    "synced_latitude",
    "synced_longitude",
    "synced_altitude_m",
}


def _baseline():
    spec = spec_from_file_location("baseline_0001", BASELINE_PATH)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_baseline_leaves_flight_log_sync_columns_to_revision_0002() -> None:
    baseline = _baseline()
    backfilled = set(baseline._IMAGES_CALIBRATION_COLUMNS) | set(
        baseline._RECONSTRUCTIONS_SHIM_COLUMNS
    )

    assert "_IMAGE_FLIGHT_LOG_SYNC_COLUMNS" not in MIGRATION
    assert not backfilled & _FLIGHT_LOG_SYNC_COLUMNS


def test_baseline_documents_shim_column_owner_convention() -> None:
    assert "Columns introduced by a numbered revision belong only" in MIGRATION


def test_baseline_is_frozen_instead_of_built_from_the_live_models() -> None:
    # A baseline built from models.py silently changes what every fresh
    # `alembic upgrade head` creates whenever a model changes (#946).
    tree = ast.parse(MIGRATION)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert not {module for module in imported if module.split(".")[0] == "backend"}
    assert "Base" not in names
