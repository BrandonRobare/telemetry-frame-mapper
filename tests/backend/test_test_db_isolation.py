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
