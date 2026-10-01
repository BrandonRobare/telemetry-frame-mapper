from __future__ import annotations

import tempfile
from pathlib import Path

from backend.db import database
from tests.conftest import test_engine


def test_backend_and_test_engine_share_a_process_local_temporary_database():
    database_path = Path(database.engine.url.database).resolve()
    test_database_path = Path(test_engine.url.database).resolve()

    assert database_path == test_database_path
    assert database_path.is_relative_to(Path(tempfile.gettempdir()).resolve())


def test_test_engine_enforces_foreign_keys_like_the_app_engine(db_engine):
    """Tests must see the FK failures production sees (#945)."""
    with database.engine.connect() as app_conn, test_engine.connect() as test_conn:
        assert app_conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert test_conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
