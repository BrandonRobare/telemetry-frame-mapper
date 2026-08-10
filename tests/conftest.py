from __future__ import annotations

# ruff: noqa: E402, I001

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

TEST_DB_URL_ENV = "PYTEST_DATABASE_URL"
TEST_DB_URL = os.environ.get(TEST_DB_URL_ENV)
if TEST_DB_URL is None:
    TEST_DB_DIR = Path(tempfile.mkdtemp(prefix=f"telemetry-frame-mapper-tests-{os.getpid()}-"))
    TEST_DB_PATH = TEST_DB_DIR / "test_drone_mapping.db"
    TEST_DB_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
    os.environ[TEST_DB_URL_ENV] = TEST_DB_URL
    _owns_test_db_dir = True
else:
    TEST_DB_PATH = Path(TEST_DB_URL.removeprefix("sqlite:///"))
    TEST_DB_DIR = TEST_DB_PATH.parent
    _owns_test_db_dir = False
os.environ["DATABASE_URL"] = TEST_DB_URL

from backend.db.database import Base, get_db
from backend.main import app
from backend.services.reconstruction import clear_rec_logs


test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def dispose_test_database():
    yield
    test_engine.dispose()
    if _owns_test_db_dir:
        shutil.rmtree(TEST_DB_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def setup_test_db():
    from backend.db import models  # noqa: F401

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session(setup_test_db):
    db = TestSessionLocal()
    app.state.test_db_session = db
    try:
        yield db
    finally:
        db.close()
        del app.state.test_db_session


@pytest.fixture(autouse=True)
def clean_tables(request):
    if "tests/backend" not in request.node.path.as_posix():
        yield
        return

    request.getfixturevalue("db_session")
    clear_rec_logs()
    yield
    clear_rec_logs()
    with TestSessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()


@pytest.fixture(scope="session")
def db_engine():
    return test_engine


@pytest.fixture
def client():
    return TestClient(app)
